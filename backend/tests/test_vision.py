import pytest
from PIL import Image
from vision.detector import detect_defects
from vision.preprocessor import preprocess_image
from io import BytesIO

def test_detector_with_black_image():
    # A blank black image has no real defect on it, so the fine-tuned
    # model finding nothing is the correct, honest result, not a bug.
    # This only checks the detector runs and returns the right shape.
    img = Image.new('RGB', (640, 640), color='black')
    detections = detect_defects(img)

    assert isinstance(detections, list)
    for d in detections:
        assert "class_name" in d
        assert "confidence" in d
        assert "bbox" in d

def test_preprocessor_rejects_small_image():
    img = Image.new('RGB', (32, 32), color='white')
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_byte_arr.seek(0)
    
    with pytest.raises(ValueError, match="Image too small"):
        preprocess_image(img_byte_arr.read())

def test_preprocessor_converts_rgba_to_rgb():
    img = Image.new('RGBA', (640, 640), color=(255, 255, 255, 128))
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    processed_img = preprocess_image(img_byte_arr.read())
    assert processed_img.mode == 'RGB'


# ------------------------------------------------------------------------------------ INT8 ONNX model

from pathlib import Path  # noqa: E402

import vision.detector as detector_module  # noqa: E402

WEIGHTS = Path(__file__).resolve().parent.parent / "vision" / "weights"
SAMPLES = Path(__file__).resolve().parent / "data"
INT8 = WEIGHTS / "neu_det_yolov8n_int8.onnx"


def top_class(model, name):
    """Highest-confidence class the model reports on a real NEU-DET test image (None when it finds nothing)."""
    result = model(Image.open(SAMPLES / name).resize((224, 224)), conf=0.25, verbose=False, device="cpu")[0]
    if len(result.boxes) == 0:
        return None
    return model.names[int(result.boxes.cls[result.boxes.conf.argmax()])]


def test_int8_model_is_smaller_and_agrees_with_the_fp32_model_on_real_images():
    from ultralytics import YOLO

    fp32, int8 = YOLO(str(WEIGHTS / "neu_det_yolov8n.pt")), YOLO(str(INT8), task="detect")
    assert INT8.stat().st_size < 4e6 < (WEIGHTS / "neu_det_yolov8n.pt").stat().st_size
    names = ["crazing_271.jpg", "inclusion_271.jpg", "patches_271.jpg", "scratches_271.jpg"]
    agree = sum(top_class(fp32, n) == top_class(int8, n) for n in names)
    assert agree >= 3, f"INT8 changed the top class on {len(names) - agree} of {len(names)} images"


def test_detector_runs_on_the_int8_model(monkeypatch):
    monkeypatch.setattr(detector_module.settings, "yolo_model", str(INT8))
    detector_module.get_detector.cache_clear()
    try:
        detections = detect_defects(Image.open(SAMPLES / "scratches_271.jpg").convert("RGB"))
        assert detections and {d["class_name"] for d in detections} <= set(detector_module.SEVERITY_MAP)
        assert all(0 < d["confidence"] <= 1 for d in detections)
    finally:
        detector_module.get_detector.cache_clear()
