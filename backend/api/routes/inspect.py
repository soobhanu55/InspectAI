from fastapi import APIRouter, File, UploadFile, Form
import time
import uuid
from typing import Optional

from vision.preprocessor import preprocess_image
from vision.detector import detect_defects
from agents.orchestrator import OrchestratorAgent
from mlops.logger import log_inspection
from mlops.metrics import record_inspection_metrics

router = APIRouter()

@router.post("/inspect")
async def inspect_image(
    file: UploadFile = File(...),
    machine: str = Form(...),
    part_type: str = Form(...),
    batch_id: str = Form(default=""),
):
    start = time.time()
    inspection_id = str(uuid.uuid4())
    
    # 1. Read and preprocess image
    image_bytes = await file.read()
    image = preprocess_image(image_bytes)
    
    # 2. Vision detection
    detections = detect_defects(image)
    
    # 3. Run LangGraph agent pipeline
    orchestrator = OrchestratorAgent()
    result = await orchestrator.ainvoke({
        "defect_type": detections[0]["class_name"] if detections else "ok",
        "severity": detections[0]["severity"] if detections else "none",
        "machine": machine,
        "part_type": part_type,
        "detections": detections,
        "messages": []
    })
    
    # 4. Record to SQLite log
    await log_inspection(inspection_id, machine, part_type, detections, result)
    
    # 5. Update Prometheus metrics
    record_inspection_metrics(machine, detections)
    
    latency_ms = int((time.time() - start) * 1000)
    
    return {
        "inspection_id": inspection_id,
        "detections": detections,
        "root_cause": result.get("root_cause", ""),
        "action_plan": result.get("action_plan", []),
        "eu_ai_act_tier": result.get("eu_ai_act_tier", "Minimal Risk (Art. 6)"),
        "estimated_savings_eur": result.get("estimated_savings_eur", 0),
        "agent_steps": result.get("agent_steps", []),
        "latency_ms": latency_ms,
    }
