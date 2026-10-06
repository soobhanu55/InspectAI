"""Frame transport. Cameras (producers) publish frames; inspection workers (consumers) read them.

RedisStreamBroker uses a Redis Stream with a consumer group, so several workers share the load and each frame goes
to exactly one of them. A frame stays "pending" until the worker acknowledges it after processing (at-least-once
delivery); frames held by a crashed worker are taken over with `reclaim`. The stream is capped (`maxlen`): if the
workers fall behind, the OLDEST frames are dropped rather than memory growing without bound, which for live
inspection is the right trade (a stale frame of a part that has already left the line is worthless).
InMemoryBroker has the same semantics for tests and for running without Redis.
"""
from __future__ import annotations

import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Frame:
    frame_id: str
    machine: str
    part_type: str
    image: bytes
    captured_at: float = field(default_factory=time.time)
    meta: dict = field(default_factory=dict)


class Broker(Protocol):
    def publish(self, frame: Frame) -> str: ...
    def read(self, consumer: str, count: int = 8, block_ms: int = 500) -> list[tuple[str, Frame]]: ...
    def ack(self, entry_id: str) -> None: ...
    def reclaim(self, consumer: str, min_idle_ms: int = 30_000, count: int = 8) -> list[tuple[str, Frame]]: ...
    def lag(self) -> int: ...


class InMemoryBroker:
    """Single-process stand-in with the same delivery semantics (one delivery per frame, ack, reclaim, bounded)."""

    def __init__(self, maxlen: int = 10_000, clock=time.monotonic):
        self.maxlen, self.clock = maxlen, clock
        self._next = 0
        self._queue: OrderedDict[str, Frame] = OrderedDict()  # not yet delivered
        self._pending: dict[str, tuple[Frame, str, float]] = {}  # delivered, not acked: entry -> (frame, consumer, when)
        self.dropped = 0

    def publish(self, frame: Frame) -> str:
        entry_id = f"{self._next}-0"
        self._next += 1
        self._queue[entry_id] = frame
        while len(self._queue) > self.maxlen:
            self._queue.popitem(last=False)
            self.dropped += 1
        return entry_id

    def read(self, consumer: str, count: int = 8, block_ms: int = 0) -> list[tuple[str, Frame]]:
        out = []
        while self._queue and len(out) < count:
            entry_id, frame = self._queue.popitem(last=False)
            self._pending[entry_id] = (frame, consumer, self.clock())
            out.append((entry_id, frame))
        return out

    def ack(self, entry_id: str) -> None:
        self._pending.pop(entry_id, None)

    def reclaim(self, consumer: str, min_idle_ms: int = 30_000, count: int = 8) -> list[tuple[str, Frame]]:
        now, out = self.clock(), []
        for entry_id, (frame, _, when) in list(self._pending.items()):
            if len(out) < count and (now - when) * 1000 >= min_idle_ms:
                self._pending[entry_id] = (frame, consumer, now)
                out.append((entry_id, frame))
        return out

    def lag(self) -> int:
        return len(self._queue) + len(self._pending)


class RedisStreamBroker:
    """Redis Streams. `client` must be a redis.Redis created WITHOUT decode_responses (frames carry raw image bytes)."""

    def __init__(self, client, stream: str = "inspectai:frames", group: str = "inspectors", maxlen: int = 10_000):
        self.r, self.stream, self.group, self.maxlen = client, stream, group, maxlen
        self._group_ready = False

    def _ensure_group(self) -> None:
        if self._group_ready:
            return
        try:
            self.r.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except Exception as exc:  # BUSYGROUP: the group already exists
            if "BUSYGROUP" not in str(exc):
                raise
        self._group_ready = True

    def publish(self, frame: Frame) -> str:
        fields = {"frame_id": frame.frame_id, "machine": frame.machine, "part_type": frame.part_type,
                  "captured_at": repr(frame.captured_at), "meta": json.dumps(frame.meta), "image": frame.image}
        self._ensure_group()
        entry_id = self.r.xadd(self.stream, fields, maxlen=self.maxlen, approximate=False)
        return entry_id.decode() if isinstance(entry_id, bytes) else entry_id

    @staticmethod
    def _decode(fields: dict) -> Frame:
        f = {(k.decode() if isinstance(k, bytes) else k): v for k, v in fields.items()}
        text = lambda v: v.decode() if isinstance(v, bytes) else v
        return Frame(text(f["frame_id"]), text(f["machine"]), text(f["part_type"]), f["image"],
                     float(text(f["captured_at"])), json.loads(text(f["meta"])))

    def _decoded(self, entries) -> list[tuple[str, Frame]]:
        return [((eid.decode() if isinstance(eid, bytes) else eid), self._decode(fields)) for eid, fields in entries]

    def read(self, consumer: str, count: int = 8, block_ms: int = 500) -> list[tuple[str, Frame]]:
        self._ensure_group()
        resp = self.r.xreadgroup(self.group, consumer, {self.stream: ">"}, count=count, block=block_ms or None)
        return self._decoded(resp[0][1]) if resp else []

    def ack(self, entry_id: str) -> None:
        self.r.xack(self.stream, self.group, entry_id)

    def reclaim(self, consumer: str, min_idle_ms: int = 30_000, count: int = 8) -> list[tuple[str, Frame]]:
        """Take over frames that another consumer read but never acknowledged (it probably crashed)."""
        self._ensure_group()
        result = self.r.xautoclaim(self.stream, self.group, consumer, min_idle_time=min_idle_ms, start_id="0-0", count=count)
        return self._decoded(result[1])

    def lag(self) -> int:
        """Frames not yet delivered plus frames delivered but not acknowledged."""
        self._ensure_group()
        info = next(g for g in self.r.xinfo_groups(self.stream) if (g["name"].decode() if isinstance(g["name"], bytes) else g["name"]) == self.group)
        last = info["last-delivered-id"]
        last = last.decode() if isinstance(last, bytes) else last
        undelivered = len(self.r.xrange(self.stream, min=f"({last}", max="+", count=100_000))
        return undelivered + int(info["pending"])
