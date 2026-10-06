"""Alerts and where they go. A sink must never raise: a broken webhook must not stop the inspection stream."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Protocol

import httpx
import structlog

logger = structlog.get_logger()


@dataclass
class Alert:
    name: str
    status: str  # "firing" or "resolved"
    severity: str  # "critical" | "warning" | "info"
    message: str
    frame_index: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    details: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


class AlertSink(Protocol):
    def emit(self, alert: Alert) -> None: ...


class MemorySink:
    def __init__(self) -> None:
        self.alerts: list[Alert] = []

    def emit(self, alert: Alert) -> None:
        self.alerts.append(alert)


class LogSink:
    def emit(self, alert: Alert) -> None:
        log = logger.error if alert.status == "firing" and alert.severity == "critical" else logger.warning
        log("alert", name=alert.name, status=alert.status, severity=alert.severity, message=alert.message,
            frame_index=alert.frame_index)


class WebhookSink:
    """POSTs {"text": ...} to a Slack-compatible webhook URL (from the environment, never hardcoded). Failures are
    counted and logged, not raised."""

    def __init__(self, url: str, client: httpx.Client | None = None, timeout: float = 5.0):
        self.url, self.client, self.timeout = url, client or httpx.Client(timeout=timeout), timeout
        self.failures = 0

    def emit(self, alert: Alert) -> None:
        icon = {"critical": "[CRITICAL]", "warning": "[WARNING]", "info": "[OK]"}.get(alert.severity, "")
        try:
            self.client.post(self.url, json={"text": f"{icon} {alert.name} {alert.status}: {alert.message}"}).raise_for_status()
        except Exception as exc:
            self.failures += 1
            logger.warning("alert_webhook_failed", error=type(exc).__name__)
