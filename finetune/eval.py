"""Honest before/after comparison on the NEU-DET held-out test split (180 images).

Prints real mAP50 and mAP50-95 for:
  1. stock yolov8n.pt (COCO-pretrained, never seen a steel defect)
  2. the fine-tuned weights from runs/neu_det_yolov8n/weights/best.pt

Both numbers are measured, not assumed, same standard as the rest of this repo.
"""
import sys
from ultralytics import YOLO

def evaluate(weights, label):
    print(f"\n=== {label} ({weights}) ===")
    model = YOLO(weights)
    metrics = model.val(data="data.yaml", imgsz=200, split="val")
    print(f"{label}: mAP50={metrics.box.map50:.4f}  mAP50-95={metrics.box.map:.4f}")
    for i in range(len(metrics.box.ap50)):
        print(f"  {metrics.names.get(i, i)}: AP50={metrics.box.ap50[i]:.4f}")
    return metrics.box.map50, metrics.box.map

if __name__ == "__main__":
    finetuned_path = sys.argv[1] if len(sys.argv) > 1 else "runs/neu_det_yolov8n/weights/best.pt"

    base_map50, base_map = evaluate("yolov8n.pt", "Baseline (stock, COCO-pretrained)")
    ft_map50, ft_map = evaluate(finetuned_path, "Fine-tuned (NEU-DET)")

    print("\n=== Summary ===")
    print(f"mAP50:    {base_map50:.4f} -> {ft_map50:.4f}")
    print(f"mAP50-95: {base_map:.4f} -> {ft_map:.4f}")
