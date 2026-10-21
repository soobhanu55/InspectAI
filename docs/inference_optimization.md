# Inference optimisation of the defect detector

The NEU-DET YOLOv8n (`backend/vision/weights/neu_det_yolov8n.pt`) exported to ONNX and quantised to INT8, measured against the
PyTorch model. Reproduce: `python finetune/optimize.py --weights backend/vision/weights/neu_det_yolov8n.pt --images DIR/images --labels DIR/labels`
(the 180 held-out test images with YOLO labels); raw numbers in `docs/inference_optimization.json`.

## Method

* The 180 test images are split once, per class, with a fixed seed: **60 calibration** images (10 per class, used only to calibrate
  INT8) and **120 evaluation** images (20 per class). Every variant is scored on the same 120, so calibration data never leaks into the
  accuracy numbers. (The 0.7498 mAP50 in `finetune/README.md` is the official 180-image score with PyTorch's rectangular evaluation;
  numbers here are lower and not comparable to it, see below.)
* Accuracy: mAP50 and mAP50-95 from Ultralytics' validator at 224x224, `rect=False` for every variant, because an exported model has a
  fixed input shape. PyTorch's default rectangular batching scores 0.735 on these 120; the exported models cannot use it.
* Latency: the network alone (no pre- or post-processing), one 224x224 image, CPU, ONNX Runtime 1.26 vs PyTorch 2.6 (fused conv+BN),
  Intel Core i7-12650H laptop. The variants are timed in alternating rounds (8 x 100 runs each) so a changing laptop clock hits all of
  them equally.

## Results

| Variant | Size | mAP50 | mAP50-95 | CPU latency, 1 thread (p50) | Speed-up vs PyTorch |
|---|---|---|---|---|---|
| PyTorch FP32 (baseline) | 6.2 MB (checkpoint stored in FP16) | 0.688 | 0.374 | 15.8 ms | 1.0x |
| ONNX FP32 | 12.1 MB | 0.688 | 0.374 | 9.7 ms | 1.6x |
| **ONNX INT8, percentile calibration (shipped)** | **3.3 MB** | **0.679** | **0.362** | **5.3 ms** | **3.0x** |
| ONNX INT8, min-max calibration | 3.3 MB | 0.678 | 0.365 | 5.4 ms | 2.9x |
| ONNX INT8, detection head kept in FP32 | 5.5 MB | 0.676 | 0.363 | 7.3 ms | 2.2x |

The INT8 model is 3.7x smaller than the ONNX FP32 file and 3.0x faster than PyTorch on one CPU thread, for a 0.9-point drop in mAP50
(0.688 to 0.679). On 120 images a one-point difference is within noise; I did not test it for significance. Keeping the head in FP32
costs speed and size and did not help accuracy, so it is not used.

## What the work found

1. **The ONNX export is lossless.** Raw outputs differ from PyTorch by at most 0.001 and mAP is identical (0.6883) when both are scored
   the same way. The 5-point gap I first saw (0.735 vs 0.688) came from PyTorch's rectangular evaluation, not from the export.
2. **The first INT8 model scored mAP 0.0.** Quantising every operator also quantised the SiLU activations (Sigmoid and Mul), and every
   class score collapsed to exactly zero while the box coordinates still looked plausible. Checking the class scores, then quantising
   convolutions only (`op_types_to_quantize=["Conv"]`), fixed it; scores then match FP32 to about 0.02.
3. **Wiring:** `YOLO_MODEL=vision/weights/neu_det_yolov8n_int8.onnx` switches the service to the INT8 model (`onnxruntime` is a
   dependency; the detector forces the CPU provider). The default stays the PyTorch model; the Kubernetes manifests were not changed
   or re-tested with the INT8 model. Tests check it is smaller than the FP32 checkpoint, agrees with it on the top class on 3 of 4 real images, and runs
   through `detect_defects`.

## Limits

* One laptop CPU and a 224-pixel input. The 4-thread numbers are not reported as results: median latency swung from 4 ms to 13 ms
  between rounds (p95 up to 120 ms) because of laptop scheduling. GPU numbers were equally unstable and are omitted.
* Network time only; image decoding, resizing and non-maximum suppression add to the real request latency.
* INT8 calibration used 60 images of the same dataset; a production line with a different camera would need its own calibration set.
* 120 evaluation images and one split: no confidence interval on the accuracy cost.
