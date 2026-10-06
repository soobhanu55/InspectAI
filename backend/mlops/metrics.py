from prometheus_client import Counter, Gauge, Histogram

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
    "Preprocessing plus YOLOv8 inference latency per frame",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5]
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
    "Share of the last 100 frames of a machine with at least one detection",
    ["machine"]
)

# --- stream worker ---
STREAM_FRAMES = Counter(
    "fertigungsai_stream_frames_total",
    "Frames taken from the stream, by outcome (ok, dead_letter, error)",
    ["status"]
)
STREAM_QUEUE_DELAY = Histogram(
    "fertigungsai_stream_queue_delay_seconds",
    "Time from capture to the start of processing",
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60]
)
STREAM_LAG = Gauge("fertigungsai_stream_lag_frames", "Frames waiting in the stream plus frames in flight")
ALERTS = Counter("fertigungsai_alerts_total", "Alert events", ["alert", "status"])


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
