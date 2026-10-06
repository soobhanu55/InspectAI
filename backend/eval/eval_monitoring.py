"""Measure the stream monitor on real detector output.

    python eval/eval_monitoring.py --images path/to/NEU-DET/test/images      # from backend/; writes ../docs/monitoring_eval.md

1. The real fine-tuned YOLOv8n runs over the HELD-OUT NEU-DET test images (never the training images) clean and
   with three camera faults (blur, low light, sensor noise); each result is reduced to a FrameRecord. The 180 images
   are split by position: the even-indexed half was used to diagnose and fix the monitor's false alarms, the report
   is produced on the odd-indexed half, which that work never touched (--half odd, the default).
2. Streams of 900 frames are sampled from those records: in control for 450 frames, then a fault begins (or not).
   The first 150 frames are the monitor's baseline. 200 random streams per scenario go through the real StreamMonitor
   with its default settings, and we count (a) alerts BEFORE the change = false alarms, (b) how many frames after the
   change the first alert took.
3. Throughput: the real Worker (decode, YOLO, SQLite log, monitor) processes frames from an in-memory broker.

Caveats stated in the report: the images are re-sampled with replacement; every NEU-DET image contains a
defect, so a "defect-rate" shift is only visible when a fault stops the detector from seeing them; the latency
scenario is simulated (inference time x3), the others use real images and the real detector.
"""
from __future__ import annotations

import argparse
import io
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monitoring.monitor import StreamMonitor  # noqa: E402
from monitoring.records import FrameRecord  # noqa: E402
from streaming.broker import Frame, InMemoryBroker  # noqa: E402
from streaming.producer import apply_fault, to_jpeg  # noqa: E402
from streaming.worker import FrameProcessor, Worker  # noqa: E402

N_RUNS, N_FRAMES, CHANGE_AT, WINDOW_AFTER = 200, 900, 450, 150
CONDITIONS = ["none", "blur", "dark", "noise"]
SCENARIOS = [  # name, post-change condition, extra
    ("healthy (no change)", None),
    ("blurred lens", "blur"),
    ("lights fail (50% brightness)", "dark"),
    ("sensor noise", "noise"),
    ("defect-class mix shifts to 80% scratches", "mix"),
    ("inference 3x slower (simulated)", "slow"),
]


def build_records(paths: list[Path]) -> tuple[dict, list[str]]:
    """Run the real detector on every test image under every condition (once each)."""
    from vision.detector import detect_defects
    from vision.preprocessor import preprocess_image

    proc = FrameProcessor(detect_defects, preprocess_image)
    rng = np.random.default_rng(0)
    proc.process(Frame("warmup", "M", "p", paths[0].read_bytes()))  # first call loads the model; do not time it
    records, classes = {}, []
    for p in paths:
        classes.append(p.stem.rsplit("_", 1)[0])  # ground-truth class from the file name, e.g. scratches_12
        base = Image.open(p)
        for cond in CONDITIONS:
            raw = p.read_bytes() if cond == "none" else to_jpeg(apply_fault(base, cond, rng))
            records[(p.name, cond)] = proc.process(Frame(p.name, "M1", "strip", raw)).record
    return records, classes


def sample_stream(rng, names, classes, records, post, n=N_FRAMES):
    scratches = [i for i, c in enumerate(classes) if c == "scratches"]
    out = []
    for t in range(n):
        changed = post is not None and t >= CHANGE_AT
        if changed and post == "mix":
            idx = int(rng.choice(scratches)) if rng.random() < 0.8 else int(rng.integers(len(names)))
        else:
            idx = int(rng.integers(len(names)))
        cond = post if changed and post in CONDITIONS else "none"
        rec = records[(names[idx], cond)]
        if changed and post == "slow":
            rec = FrameRecord(rec.has_defect, rec.top_class, rec.confidence, rec.brightness, rec.contrast, rec.sharpness, rec.latency_ms * 3)
        out.append(rec)
    return out


def run_scenario(post, names, classes, records, seed0=0):
    delays, fired_by, false_alarm_runs, detected, false_by = [], Counter(), 0, 0, Counter()
    for k in range(N_RUNS):
        rng = np.random.default_rng(seed0 + k)
        monitor, first_after, names_after, false_alarm, false_names = StreamMonitor(), None, set(), False, set()
        for t, rec in enumerate(sample_stream(rng, names, classes, records, post), start=1):
            for a in monitor.observe(rec):
                if a.status != "firing":
                    continue
                if post is None or t <= CHANGE_AT:
                    false_alarm = True
                    false_names.add(a.name)
                elif t <= CHANGE_AT + WINDOW_AFTER:
                    first_after = first_after or t
                    names_after.add(a.name)
        false_alarm_runs += false_alarm
        false_by.update(false_names)
        if first_after:
            detected += 1
            delays.append(first_after - CHANGE_AT)
            fired_by.update(names_after)
    return {"detected": detected, "delays": delays, "fired_by": fired_by, "false_alarm_runs": false_alarm_runs, "false_by": false_by}


def measure_throughput(paths: list[Path], n: int = 300) -> dict:
    from mlops import logger
    from vision.detector import detect_defects
    from vision.preprocessor import preprocess_image

    db = Path(tempfile.mkdtemp()) / "throughput.db"
    logger.settings.sqlite_db = str(db)
    logger._init_db()
    broker = InMemoryBroker()
    for i in range(n):
        broker.publish(Frame(f"t{i}", "M1", "strip", paths[i % len(paths)].read_bytes()))

    def record(frame, result):
        return logger.record_inspection(frame.frame_id, frame.machine, frame.part_type, result.detections,
                                        latency_ms=result.latency_ms, source="stream")

    w = Worker(broker, FrameProcessor(detect_defects, preprocess_image), StreamMonitor(), record=record, block_ms=0)
    start = time.perf_counter()
    while w.step():
        pass
    seconds = time.perf_counter() - start
    logged = logger._get_db().execute("SELECT COUNT(*) FROM inspections").fetchone()[0]
    return {"frames": n, "seconds": seconds, "fps": n / seconds, "logged": logged, "lag": broker.lag(), "stats": dict(w.stats)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True, help="folder with the NEU-DET held-out test images")
    ap.add_argument("--half", choices=["all", "even", "odd"], default="odd")
    args = ap.parse_args()
    paths = sorted(Path(args.images).glob("*.jpg"))
    assert len(paths) == 180, f"expected the 180 held-out test images, found {len(paths)}"
    paths = {"all": paths, "even": paths[0::2], "odd": paths[1::2]}[args.half]

    print("running the detector over", len(paths), "images x", len(CONDITIONS), "conditions ...", flush=True)
    records, classes = build_records(paths)
    names = [p.name for p in paths]

    hit = {c: np.mean([records[(n, c)].has_defect for n in names]) for c in CONDITIONS}
    conf = {c: np.mean([records[(n, c)].confidence for n in names if records[(n, c)].has_defect] or [0]) for c in CONDITIONS}
    lat = np.median([records[(n, "none")].latency_ms for n in names])

    lines = [
        "# Monitoring evaluation on real detector output\n",
        f"Real fine-tuned YOLOv8n on {len(paths)} held-out NEU-DET test images (the {args.half} half of the 180; the training images are never used). "
        f"Streams of {N_FRAMES} frames are sampled with replacement; the first 150 frames are the baseline; a fault starts at frame "
        f"{CHANGE_AT}; {N_RUNS} random streams per scenario go through the real `StreamMonitor` with its default settings. "
        f"\"Detected\" means an alert fired within {WINDOW_AFTER} frames of the change.\n",
        "## What the detector sees under each condition\n",
        "| Condition | Frames with a detection | Mean confidence of detections |", "|---|---|---|",
        *[f"| {c} | {hit[c]:.0%} | {conf[c]:.2f} |" for c in CONDITIONS],
        f"\nMedian preprocessing + inference time per frame: {lat:.1f} ms. Every NEU-DET image contains a defect, so the "
        "'with a detection' share is the detector's hit rate on genuinely defective parts.\n",
        "## Detection and false alarms\n",
        "| Scenario | Detected | Median delay (frames) | 90th percentile | Alerts that fired | False alarm before the change |",
        "|---|---|---|---|---|---|",
    ]
    pre_change_total = pre_change_alarms = 0
    false_by_all: Counter = Counter()
    for name, post in SCENARIOS:
        r = run_scenario(post, names, classes, records)
        pre_change_total += N_RUNS
        pre_change_alarms += r["false_alarm_runs"]
        false_by_all.update(r["false_by"])
        if post is None:
            lines.append(f"| {name} | n/a | n/a | n/a | n/a | {r['false_alarm_runs']}/{N_RUNS} runs ({r['false_alarm_runs'] / N_RUNS:.1%}) |")
        else:
            d = np.array(r["delays"])
            fired = ", ".join(f"{k} ({v})" for k, v in r["fired_by"].most_common()) or "none"
            med = f"{np.median(d):.0f}" if len(d) else "n/a"
            p90 = f"{np.percentile(d, 90):.0f}" if len(d) else "n/a"
            lines.append(f"| {name} | {r['detected']}/{N_RUNS} ({r['detected'] / N_RUNS:.0%}) | {med} | {p90} | {fired} | "
                         f"{r['false_alarm_runs']}/{N_RUNS} ({r['false_alarm_runs'] / N_RUNS:.1%}) |")
        print(lines[-1], flush=True)
    lines.append(f"\nFalse alarms pooled over every scenario's pre-change segment: {pre_change_alarms}/{pre_change_total} runs "
                 f"({pre_change_alarms / pre_change_total:.1%}) raised at least one alert before any fault"
                 + (f" (by detector: {dict(false_by_all)})" if false_by_all else "") + ".\n")

    lines += [
        "## History: what the first run showed, and what changed\n",
        "The first version of the monitor (all 180 images) detected every fault within 20 to 60 frames, but **15% of healthy runs "
        "(30 of 200) and 5.8% of pre-fault segments overall (70 of 1,200) raised a false alarm**, against about 1% on the "
        "synthetic healthy streams the thresholds had been chosen on. Breaking it down on the even-indexed half only: every false "
        "alarm came from the defect-rate control chart (mean +/- 3.5 sigma), none from the drift tests. The detector finds a defect in "
        "about 97% of clean frames; near 100% the number of missed frames per window is a skewed count and normal-approximation limits "
        "are far too tight in the upper tail. The chart was replaced by Fisher's exact test, which dropped the even half to 0 of 300 "
        "false-alarming runs. This report is on the odd half, which none of that work looked at. The thresholds themselves "
        "(alpha 1e-4, two consecutive checks) were not changed.\n",
    ]
    print("measuring worker throughput ...", flush=True)
    t = measure_throughput(paths)
    lines += [
        "## Worker throughput\n",
        f"The real `Worker` (decode, YOLOv8n, SQLite log, monitor) processed {t['frames']} frames from an in-memory broker in "
        f"{t['seconds']:.1f} s = **{t['fps']:.0f} frames/s** on one process; {t['logged']} rows were logged, lag at the end {t['lag']}. "
        "Hardware: a laptop RTX 4050; the number depends heavily on the machine, varied roughly twofold between runs (38 to 84 frames/s over four runs), "
        "and is not a Redis benchmark.\n",
        "## Caveats\n",
        f"- Only {len(paths)} distinct images, re-sampled with replacement; real production drift is slower and messier than these step changes.",
        "- Every NEU-DET image shows a defect, so there are no healthy-part frames; a surge in defects is not tested here, only "
        "faults that change what the detector sees.",
        "- The latency scenario multiplies measured inference times by 3; the other scenarios use real images and the real detector.",
        "- The significance levels (alpha 1e-4, two consecutive checks) were chosen from a false-alarm budget on synthetic healthy streams before any "
        "real-image run. The defect-rate test WAS replaced after the first real-image run (see History); that fix was diagnosed on the other half of the images.",
        "- One 900-frame step change per run and 200 runs per scenario, so a rate like 0.5% (1 of 200) is imprecise.",
        "",
    ]
    text = "\n".join(lines)
    out = Path(__file__).resolve().parent.parent.parent / "docs" / "monitoring_eval.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
