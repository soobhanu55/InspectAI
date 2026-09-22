"""Fine-tune YOLOv8n on NEU-DET (real steel surface defect data, 6 classes).

Baseline for comparison: stock yolov8n.pt is trained on COCO, which has none
of these classes, so its "accuracy" on this dataset is effectively zero by
construction. The honest baseline in eval.py measures that directly rather
than assuming it.
"""
from ultralytics import YOLO

def main():
    model = YOLO("yolov8n.pt")  # COCO-pretrained weights, fine-tuned from here
    model.train(
        data="data.yaml",
        epochs=100,
        imgsz=200,          # NEU-DET images are 200x200
        batch=16,
        patience=20,
        project="runs",
        name="neu_det_yolov8n",
        seed=0,
    )

if __name__ == "__main__":
    main()
