# Monitoring evaluation on real detector output

Real fine-tuned YOLOv8n on 90 held-out NEU-DET test images (the odd half of the 180; the training images are never used). Streams of 900 frames are sampled with replacement; the first 150 frames are the baseline; a fault starts at frame 450; 200 random streams per scenario go through the real `StreamMonitor` with its default settings. "Detected" means an alert fired within 150 frames of the change.

## What the detector sees under each condition

| Condition | Frames with a detection | Mean confidence of detections |
|---|---|---|
| none | 98% | 0.66 |
| blur | 91% | 0.58 |
| dark | 98% | 0.63 |
| noise | 34% | 0.39 |

Median preprocessing + inference time per frame: 7.9 ms. Every NEU-DET image contains a defect, so the 'with a detection' share is the detector's hit rate on genuinely defective parts.

## Detection and false alarms

| Scenario | Detected | Median delay (frames) | 90th percentile | Alerts that fired | False alarm before the change |
|---|---|---|---|---|---|
| healthy (no change) | n/a | n/a | n/a | n/a | 1/200 runs (0.5%) |
| blurred lens | 200/200 (100%) | 40 | 40 | drift_sharpness (200), class_mix_drift (200), drift_confidence (127), drift_contrast (50), defect_rate (8) | 0/200 (0.0%) |
| lights fail (50% brightness) | 200/200 (100%) | 50 | 60 | drift_contrast (200), drift_brightness (200), drift_sharpness (198) | 0/200 (0.0%) |
| sensor noise | 200/200 (100%) | 40 | 40 | drift_sharpness (200), drift_contrast (200), defect_rate (200), drift_confidence (200), class_mix_drift (186) | 0/200 (0.0%) |
| defect-class mix shifts to 80% scratches | 200/200 (100%) | 60 | 70 | drift_sharpness (200), class_mix_drift (200), drift_brightness (166), drift_contrast (104), drift_confidence (26) | 0/200 (0.0%) |
| inference 3x slower (simulated) | 200/200 (100%) | 20 | 20 | latency_slo (200) | 0/200 (0.0%) |

False alarms pooled over every scenario's pre-change segment: 1/1200 runs (0.1%) raised at least one alert before any fault (by detector: {'drift_confidence': 1}).

## History: what the first run showed, and what changed

The first version of the monitor (all 180 images) detected every fault within 20 to 60 frames, but **15% of healthy runs (30 of 200) and 5.8% of pre-fault segments overall (70 of 1,200) raised a false alarm**, against about 1% on the synthetic healthy streams the thresholds had been chosen on. Breaking it down on the even-indexed half only: every false alarm came from the defect-rate control chart (mean +/- 3.5 sigma), none from the drift tests. The detector finds a defect in about 97% of clean frames; near 100% the number of missed frames per window is a skewed count and normal-approximation limits are far too tight in the upper tail. The chart was replaced by Fisher's exact test, which dropped the even half to 0 of 300 false-alarming runs. This report is on the odd half, which none of that work looked at. The thresholds themselves (alpha 1e-4, two consecutive checks) were not changed.

## Worker throughput

The real `Worker` (decode, YOLOv8n, SQLite log, monitor) processed 300 frames from an in-memory broker in 3.7 s = **81 frames/s** on one process; 300 rows were logged, lag at the end 0. Hardware: a laptop RTX 4050; the number depends heavily on the machine, varied roughly twofold between runs (38 to 84 frames/s over four runs), and is not a Redis benchmark.

## Caveats

- Only 90 distinct images, re-sampled with replacement; real production drift is slower and messier than these step changes.
- Every NEU-DET image shows a defect, so there are no healthy-part frames; a surge in defects is not tested here, only faults that change what the detector sees.
- The latency scenario multiplies measured inference times by 3; the other scenarios use real images and the real detector.
- The significance levels (alpha 1e-4, two consecutive checks) were chosen from a false-alarm budget on synthetic healthy streams before any real-image run. The defect-rate test WAS replaced after the first real-image run (see History); that fix was diagnosed on the other half of the images.
- One 900-frame step change per run and 200 runs per scenario, so a rate like 0.5% (1 of 200) is imprecise.
