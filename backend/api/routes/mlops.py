import asyncio
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from config import get_settings
from mlops.logger import (get_metrics_data, get_open_alerts, get_recent_alerts, get_recent_inspections,
                          stream_summary)

router = APIRouter()

@router.get("/mlops/metrics")
async def get_mlops_dashboard_metrics():
    # Returns JSON metrics for the React dashboard
    return await get_metrics_data()

@router.get("/mlops/alerts")
async def get_alerts(limit: int = 50):
    """Alerts currently firing, and the most recent alert events (fired and resolved)."""
    return {"open": get_open_alerts(), "recent": get_recent_alerts(limit)}


@router.get("/stream/status")
async def stream_status():
    """Is the stream configured, how far behind are the workers, and what has been processed from it."""
    redis_url = get_settings().redis_url
    lag, error = None, None
    if redis_url:
        try:
            import redis

            from streaming.broker import RedisStreamBroker

            lag = RedisStreamBroker(redis.Redis.from_url(redis_url, socket_timeout=2)).lag()
        except Exception as exc:  # the API stays up if Redis is down
            error = type(exc).__name__
    return {"configured": bool(redis_url), "lag": lag, "error": error, **stream_summary()}


@router.get("/mlops/timeseries")
async def timeseries(machine: str | None = None, minutes: int = Query(60, ge=1, le=43200),
                     bucket: Literal["10 seconds", "1 minute", "5 minutes", "1 hour"] = "1 minute"):
    """Defect rate and latency per time bucket from TimescaleDB (needs TIMESCALE_URL; empty list if unset)."""
    url = get_settings().timescale_url
    if not url:
        return {"configured": False, "buckets": [], "error": None}
    try:
        from mlops.timeseries import query_series

        rows = await asyncio.to_thread(query_series, url, machine, minutes, bucket)
        return {"configured": True, "buckets": rows, "error": None}
    except Exception as exc:  # the API stays up if the database is down
        return {"configured": True, "buckets": [], "error": type(exc).__name__}


@router.get("/log")
async def get_inspection_logs(limit: int = 50):
    # Returns recent inspections for the React production log table
    return await get_recent_inspections(limit)

@router.get("/metrics")
async def get_prometheus_metrics():
    # Returns prometheus format metrics
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
