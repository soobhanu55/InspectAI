from ultralytics import YOLO
from functools import lru_cache
from PIL import Image
from config import get_settings

settings = get_settings()

# Real classes from the NEU-DET fine-tune, see finetune/README.md for the
# measured mAP per class (0.945 down to 0.449, crazing is the weak one).
SEVERITY_MAP = {
    "crazing": "medium",
    "inclusion": "medium",
    "patches": "low",
    "pitted_surface": "medium",
    "rolled-in_scale": "low",
    "scratches": "medium",
}

@lru_cache()
def get_detector():
    return YOLO(settings.yolo_model)

def detect_defects(image: Image.Image) -> list[dict]:
    """
    Run inference with the NEU-DET fine-tuned YOLOv8n (finetune/README.md).
    Real classes, real confidence scores, no simulated fallback, an empty
    result means the model genuinely found nothing above the confidence
    threshold, not that the demo needed a defect to display.
    """
    model = get_detector()

    img_resized = image.resize(
        (settings.image_size, settings.image_size)
    )

    results = model(
        img_resized,
        conf=settings.yolo_conf_threshold,
        verbose=False
    )

    detections = []
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            defect_name = model.names[cls_id]

            x1, y1, x2, y2 = box.xyxy[0].tolist()
            detections.append({
                "bbox": {
                    "x": round(x1), "y": round(y1),
                    "w": round(x2-x1), "h": round(y2-y1)
                },
                "class_name": defect_name,
                "confidence": round(float(box.conf[0]), 3),
                "severity": SEVERITY_MAP.get(defect_name, "low"),
            })

    return detections
