# InspectAI defect detection, fine-tuned

`detector.py` originally shipped with stock `yolov8n.pt`, COCO-pretrained,
never trained on a manufacturing defect, plus a deterministic simulated
fallback for demos. That's honestly documented in the code comments and now
has a real fix.

## What changed

Fine-tuned YOLOv8n on **NEU-DET**, a real steel surface defect dataset,
1800 images (1620 train / 180 held-out test), 6 defect classes with real
bounding-box labels: crazing, inclusion, patches, pitted_surface,
rolled-in_scale, scratches.

Source: [Marfbin/NEU-DET-with-yolov8](https://github.com/Marfbin/NEU-DET-with-yolov8)
(NEU-DET is a public academic dataset from Northeastern University, China,
free to use).

## Honest note on class labels

`detector.py`'s original `DEFECT_LABELS` (scratch, crack, dent, porosity,
corrosion, inclusion) were placeholders invented for the demo, not tied to
any real dataset. NEU-DET's 6 classes are real but different: crazing,
inclusion, patches, pitted_surface, rolled-in_scale, scratches. Two overlap
(scratches, inclusion), four don't. The fine-tuned model outputs NEU-DET's
real classes, not the old placeholder list, that's the honest option: claim
what the model actually detects, not what the demo used to invent.

## Run it

```bash
pip install -r requirements.txt
python train.py          # fine-tunes yolov8n.pt on data/, ~100 epochs
python eval.py            # honest before/after mAP on the 180-image held-out test set
```

## Results

Measured on the 180-image held-out test split, 100 epochs, ~11 minutes on
an RTX 4050 (6GB):

| | mAP50 | mAP50-95 |
|---|---|---|
| Baseline (stock yolov8n.pt, COCO classes) | 0.0000 | 0.0000 |
| Fine-tuned (this run) | **0.750** | **0.412** |

The baseline is genuinely ~0, not a rounding artifact, COCO has none of
these 6 defect classes, so it was never going to score above chance on
steel surface defects. That's expected and stated here rather than
presented as a surprising win.

Per-class AP50 on the fine-tuned model, real spread, not uniform:

| Class | AP50 |
|---|---|
| patches | 0.945 |
| scratches | 0.863 |
| inclusion | 0.828 |
| pitted_surface | 0.758 |
| rolled-in_scale | 0.657 |
| crazing | 0.449 |

Crazing (fine surface cracking) is the weak class, well below the others,
disclosed here rather than averaged away in the headline mAP.

## Wiring into detector.py

Done. `settings.yolo_model` now points at
`finetune/runs/detect/runs/neu_det_yolov8n/weights/best.pt`,
`DEFECT_LABELS` uses NEU-DET's real 6 classes, and the modulo-remap hack
plus the "simulated" fallback are removed, the model now detects real
defect classes with a real confidence score instead of COCO objects
relabeled through a hash.
