import pytest
from PIL import Image
from vision.detector import detect_defects
from vision.preprocessor import preprocess_image
from io import BytesIO

def test_detector_with_black_image():
    # Black image will likely result in the deterministic fallback
    img = Image.new('RGB', (640, 640), color='black')
    detections = detect_defects(img)
    
    assert len(detections) > 0
    assert "class_name" in detections[0]
    assert "confidence" in detections[0]
    assert "bbox" in detections[0]

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
