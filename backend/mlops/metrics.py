from prometheus_client import Counter, Histogram, Gauge

INSPECTIONS = Counter(
    "fertigungsai_inspections_total",
    "Total inspections",
    ["machine", "defect_type", "severity"]
)
INSPECTION_LATENCY = Histogram(
    "fertigungsai_inspection_latency_seconds",
    "End-to-end inspection latency",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)
VISION_LATENCY = Histogram(
    "fertigungsai_vision_latency_seconds",
    "YOLOv8 inference latency"
)
RAG_LATENCY = Histogram(
    "fertigungsai_rag_latency_seconds",
    "RAG retrieval latency"
)
LLM_LATENCY = Histogram(
    "fertigungsai_llm_latency_seconds",
    "Groq LLM latency"
)
DEFECT_RATE = Gauge(
    "fertigungsai_defect_rate",
    "Current defect rate",
    ["machine"]
)
RAGAS_FAITHFULNESS = Gauge("fertigungsai_ragas_faithfulness", "RAGAS evaluation score")
RAGAS_RELEVANCY = Gauge("fertigungsai_ragas_answer_relevancy", "RAGAS evaluation score")

def record_inspection_metrics(machine: str, detections: list):
    if not detections:
        INSPECTIONS.labels(machine=machine, defect_type="none", severity="none").inc()
    else:
        for d in detections:
            INSPECTIONS.labels(
                machine=machine, 
                defect_type=d["class_name"], 
                severity=d["severity"]
            ).inc()
