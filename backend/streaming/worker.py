"""Inspection worker: take frames from the broker, detect defects, log, measure, monitor, acknowledge.

    python -m streaming.worker          # reads REDIS_URL; falls back to nothing if unset

Per frame: decode -> detect -> record (SQLite, Prometheus) -> feed the StreamMonitor -> acknowledge. Only vision runs
here; the LLM root-cause agent is not called per frame (too slow and costly for a line), it stays on the /inspect path.

Failure handling: an undecodable image can never succeed, so it is counted as a dead letter and acknowledged (a poison
frame must not block the stream). Any other exception leaves the frame unacknowledged, so it can be reclaimed and
retried by this or another worker.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable

import structlog

from monitoring.alerts import Alert, AlertSink
from monitoring.features import image_stats
from monitoring.monitor import StreamMonitor
from monitoring.records import FrameRecord
from streaming.broker import Broker, Frame

logger = structlog.get_logger()


@dataclass
class FrameResult:
    frame_id: str
    machine: str
    detections: list
    latency_ms: float
    record: FrameRecord


class FrameProcessor:
    """Decode and detect one frame. `detect` and `preprocess` are injected so tests need no model."""

    def __init__(self, detect: Callable, preprocess: Callable):
        self.detect, self.preprocess = detect, preprocess

    def process(self, frame: Frame) -> FrameResult:
        start = time.perf_counter()
        image = self.preprocess(frame.image)  # ValueError / OSError for an undecodable image
        detections = self.detect(image)
        latency_ms = (time.perf_counter() - start) * 1000
        top = max(detections, key=lambda d: d["confidence"]) if detections else None
        brightness, contrast, sharpness = image_stats(image)
        record = FrameRecord(bool(detections), top["class_name"] if top else None, top["confidence"] if top else 0.0,
                             brightness, contrast, sharpness, latency_ms)
        return FrameResult(frame.frame_id, frame.machine, detections, latency_ms, record)


class Worker:
    def __init__(self, broker: Broker, processor: FrameProcessor, monitor: StreamMonitor | None = None,
                 consumer: str = "worker-1", record: Callable | None = None, metrics=None, batch: int = 8,
                 block_ms: int = 500, reclaim_idle_ms: int = 30_000):
        self.broker, self.processor, self.monitor = broker, processor, monitor
        self.consumer, self.batch, self.block_ms, self.reclaim_idle_ms = consumer, batch, block_ms, reclaim_idle_ms
        self.record = record  # record(frame, result) -> bool inserted; None disables persistence
        self.metrics = metrics  # object with the callbacks used below, or None
        self.stats = defaultdict(int)
        self._recent: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

    def _handle(self, entry_id: str, frame: Frame) -> None:
        if self.metrics:
            self.metrics.queue_delay(max(0.0, time.time() - frame.captured_at))
        try:
            result = self.processor.process(frame)
        except (ValueError, OSError) as exc:  # cannot be decoded: retrying will never help
            self.stats["dead_letter"] += 1
            logger.warning("frame_dead_letter", frame_id=frame.frame_id, error=type(exc).__name__)
            if self.metrics:
                self.metrics.frame("dead_letter")
            self.broker.ack(entry_id)
            return
        except Exception:  # leave it unacknowledged so that it can be reclaimed and retried
            self.stats["error"] += 1
            logger.exception("frame_failed", frame_id=frame.frame_id)
            if self.metrics:
                self.metrics.frame("error")
            return

        if self.record is not None and not self.record(frame, result):
            self.stats["duplicate"] += 1  # redelivered frame that was already logged: do not count it twice
            self.broker.ack(entry_id)
            return
        self.stats["ok"] += 1
        if self.metrics:
            self.metrics.frame("ok")
            self.metrics.processed(result)
            self._recent[frame.machine].append(result.record.has_defect)
            self.metrics.defect_rate(frame.machine, sum(self._recent[frame.machine]) / len(self._recent[frame.machine]))
        if self.monitor is not None:
            for alert in self.monitor.observe(result.record):
                if self.metrics:
                    self.metrics.alert(alert)
        self.broker.ack(entry_id)

    def step(self) -> int:
        """One read-process cycle. Returns the number of frames handled (0 means the stream was idle)."""
        entries = self.broker.read(self.consumer, self.batch, self.block_ms)
        if not entries:
            entries = self.broker.reclaim(self.consumer, self.reclaim_idle_ms, self.batch)
        for entry_id, frame in entries:
            self._handle(entry_id, frame)
        if self.metrics:
            self.metrics.lag(self.broker.lag())
        if not entries and self.monitor is not None:
            alert = self.monitor.check_stall()
            if alert and self.metrics:
                self.metrics.alert(alert)
        return len(entries)

    def run(self, should_stop: Callable[[], bool] = lambda: False) -> None:
        while not should_stop():
            self.step()


class PrometheusMetrics:
    """Binds the worker's callbacks to the Prometheus metrics defined in mlops.metrics."""

    def __init__(self):
        from mlops import metrics as m

        self.m = m

    def queue_delay(self, seconds): self.m.STREAM_QUEUE_DELAY.observe(seconds)
    def frame(self, status): self.m.STREAM_FRAMES.labels(status=status).inc()
    def lag(self, n): self.m.STREAM_LAG.set(n)
    def defect_rate(self, machine, rate): self.m.DEFECT_RATE.labels(machine=machine).set(rate)
    def alert(self, alert: Alert): self.m.ALERTS.labels(alert=alert.name, status=alert.status).inc()

    def processed(self, result: FrameResult):
        self.m.VISION_LATENCY.observe(result.latency_ms / 1000)
        self.m.record_inspection_metrics(result.machine, result.detections)


class SqliteAlertSink:
    def emit(self, alert: Alert) -> None:
        from mlops.logger import log_alert

        log_alert(alert)


def main() -> None:  # pragma: no cover - wiring only, exercised by the docker-compose stack
    import os
    import signal

    import redis
    from prometheus_client import start_http_server

    from monitoring.alerts import LogSink, WebhookSink
    from mlops.logger import record_inspection
    from streaming.broker import RedisStreamBroker
    from vision.detector import detect_defects
    from vision.preprocessor import preprocess_image

    broker = RedisStreamBroker(redis.Redis.from_url(os.environ["REDIS_URL"]))
    sinks: list[AlertSink] = [LogSink(), SqliteAlertSink()]
    if os.environ.get("ALERT_WEBHOOK_URL"):
        sinks.append(WebhookSink(os.environ["ALERT_WEBHOOK_URL"]))
    monitor = StreamMonitor(sinks=sinks, baseline_frames=int(os.environ.get("BASELINE_FRAMES", "150")),
                            stall_seconds=float(os.environ.get("STALL_SECONDS", "30")))

    def record(frame: Frame, result: FrameResult) -> bool:
        return record_inspection(frame.frame_id, frame.machine, frame.part_type, result.detections,
                                 latency_ms=result.latency_ms, source="stream")

    start_http_server(int(os.environ.get("WORKER_METRICS_PORT", "9108")))
    worker = Worker(broker, FrameProcessor(detect_defects, preprocess_image), monitor,
                    consumer=os.environ.get("WORKER_NAME", f"worker-{os.getpid()}"), record=record, metrics=PrometheusMetrics())
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    logger.info("worker_started", consumer=worker.consumer)
    worker.run(lambda: stop["flag"])


if __name__ == "__main__":  # pragma: no cover
    main()
