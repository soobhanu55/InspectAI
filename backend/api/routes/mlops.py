from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from mlops.logger import get_recent_inspections, get_metrics_data

router = APIRouter()

@router.get("/mlops/metrics")
async def get_mlops_dashboard_metrics():
    # Returns JSON metrics for the React dashboard
    return await get_metrics_data()

@router.get("/log")
async def get_inspection_logs(limit: int = 50):
    # Returns recent inspections for the React production log table
    return await get_recent_inspections(limit)

@router.get("/metrics")
async def get_prometheus_metrics():
    # Returns prometheus format metrics
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
