"""StreamMonitor: baseline, sliding window, debounced alerts.

The first `baseline_frames` frames are taken as in control and used to fit every detector, so they must come from
a healthy line; a monitor started during a fault will treat the fault as normal. After that the last `window`
frames are checked every `check_every` frames. An alert fires only after `consecutive` checks in a row breach
(one noisy window is not an incident), stays firing without repeating, and a `resolved` alert is emitted after
`consecutive` clean checks in a row.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Callable

from monitoring.alerts import Alert, AlertSink
from monitoring.detectors import default_detectors
from monitoring.records import FrameRecord


class StreamMonitor:
    def __init__(self, sinks: list[AlertSink] | None = None, baseline_frames: int = 150, window: int = 100,
                 check_every: int = 10, consecutive: int = 2, detectors: list | None = None,
                 stall_seconds: float | None = None, clock: Callable[[], float] = time.monotonic):
        self.sinks = list(sinks or [])
        self.baseline_frames, self.window_size, self.check_every, self.consecutive = baseline_frames, window, check_every, consecutive
        self.detectors = detectors if detectors is not None else default_detectors()
        self.stall_seconds, self.clock = stall_seconds, clock
        self.frames_seen = 0
        self._baseline: list[FrameRecord] = []
        self._window: deque[FrameRecord] = deque(maxlen=window)
        self._breaches: dict[str, int] = {}
        self._clears: dict[str, int] = {}
        self.firing: dict[str, Alert] = {}
        self._last_frame_at: float | None = None
        self._stalled = False

    @property
    def baseline_ready(self) -> bool:
        return self.frames_seen >= self.baseline_frames

    def _emit(self, alert: Alert) -> None:
        for sink in self.sinks:
            try:
                sink.emit(alert)
            except Exception:  # a failing sink must not stop the stream
                pass

    def observe(self, rec: FrameRecord) -> list[Alert]:
        """Feed one processed frame; returns the alerts that fired or resolved because of it."""
        self.frames_seen += 1
        self._last_frame_at = self.clock()
        out: list[Alert] = []
        if self._stalled:
            self._stalled = False
            out.append(Alert("stalled", "resolved", "info", "frames are arriving again", self.frames_seen))

        if self.frames_seen <= self.baseline_frames:
            self._baseline.append(rec)
            if self.frames_seen == self.baseline_frames:
                for d in self.detectors:
                    d.fit(self._baseline)
        else:
            self._window.append(rec)
            if len(self._window) == self.window_size and (self.frames_seen - self.baseline_frames) % self.check_every == 0:
                out += self._check()
        for alert in out:
            self._emit(alert)
        return out

    def _check(self) -> list[Alert]:
        window, out = list(self._window), []
        for d in self.detectors:
            breach = d.check(window)
            if breach is not None:
                self._clears[d.name] = 0
                self._breaches[d.name] = self._breaches.get(d.name, 0) + 1
                if self._breaches[d.name] >= self.consecutive and d.name not in self.firing:
                    alert = Alert(d.name, "firing", breach.severity, breach.message, self.frames_seen, details=breach.details)
                    self.firing[d.name] = alert
                    out.append(alert)
            else:
                self._breaches[d.name] = 0
                if d.name in self.firing:
                    self._clears[d.name] = self._clears.get(d.name, 0) + 1
                    if self._clears[d.name] >= self.consecutive:
                        self.firing.pop(d.name)
                        out.append(Alert(d.name, "resolved", "info", "back within the baseline", self.frames_seen))
        return out

    def check_stall(self) -> Alert | None:
        """Call periodically (e.g. when a read times out). Fires once if no frame was processed for stall_seconds."""
        if self.stall_seconds is None or self._last_frame_at is None or self._stalled:
            return None
        idle = self.clock() - self._last_frame_at
        if idle < self.stall_seconds:
            return None
        self._stalled = True
        alert = Alert("stalled", "firing", "critical", f"no frame processed for {idle:.0f} s", self.frames_seen)
        self._emit(alert)
        return alert

    def status(self) -> dict:
        return {"frames_seen": self.frames_seen, "baseline_ready": self.baseline_ready,
                "firing": [a.name for a in self.firing.values()] + (["stalled"] if self._stalled else [])}
