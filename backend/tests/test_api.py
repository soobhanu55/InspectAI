import pytest
from fastapi.testclient import TestClient
from app import app
from io import BytesIO
from PIL import Image

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_inspect_endpoint():
    # Create a synthetic white 640x640 image
    img = Image.new('RGB', (640, 640), color='white')
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_byte_arr.seek(0)
    
    response = client.post(
        "/api/inspect",
        files={"file": ("test.jpg", img_byte_arr, "image/jpeg")},
        data={"machine": "TestMachine", "part_type": "TestPart", "batch_id": "123"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "inspection_id" in data
    assert "detections" in data
    assert "root_cause" in data
    assert "action_plan" in data

def test_metrics_endpoint():
    response = client.get("/api/metrics")
    assert response.status_code == 200
    assert b"fertigungsai_inspections_total" in response.content

def test_log_endpoint():
    response = client.get("/api/log")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
