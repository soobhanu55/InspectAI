"""Builds the sample dataset in powerbi/data: one SIMULATED production day, processed by the real fine-tuned detector.

    python powerbi/make_sample_day.py --images /path/to/NEU-DET/test/images --db /tmp/day.db
    python powerbi/export_powerbi.py --db /tmp/day.db --out powerbi/data

Two machines alternate, one frame every 15 seconds in total (5,760 frames over 24 h, from 2026-09-01 00:00 UTC). From
14:00 to 17:00 machine M2's lens is out of focus (a Gaussian blur on its images). Everything else, the detections, the
latencies and the alerts, comes from the real worker and monitor; only the clock is simulated. The images are
re-sampled NEU-DET test images (not committed), so the defect mix is that dataset's, not a factory's.
"""
from __future__ import annotations

import argparse
import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

START = datetime(2026, 9, 1, tzinfo=timezone.utc)
STEP_SECONDS = 15
N_FRAMES = 24 * 3600 // STEP_SECONDS
FAULT_HOURS = range(14, 17)


def simulated_frames(paths: list[Path], seed: int = 0):
    from streaming.broker import Frame
    from streaming.producer import apply_fault, to_jpeg

    rng = random.Random(seed)
    for i in range(N_FRAMES):
        t = START + timedelta(seconds=STEP_SECONDS * i)
        machine = "M1" if i % 2 == 0 else "M2"
        path = rng.choice(paths)
        faulty = machine == "M2" and t.hour in FAULT_HOURS
        image = to_jpeg(apply_fault(Image.open(path), "blur")) if faulty else path.read_bytes()
        yield t, Frame(f"{machine}-{i:05d}", machine, "steel-strip", image, captured_at=t.timestamp(),
                       meta={"fault": "blur" if faulty else "none"})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    from mlops import logger

    Path(args.db).unlink(missing_ok=True)
    logger.settings.sqlite_db = args.db
    logger._init_db()

    from monitoring.monitor import StreamMonitor
    from streaming.broker import InMemoryBroker
    from streaming.worker import FrameProcessor, SqliteAlertSink, Worker
    from vision.detector import detect_defects
    from vision.preprocessor import preprocess_image

    paths = sorted(p for p in Path(args.images).iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"})
    broker = InMemoryBroker(maxlen=N_FRAMES + 10)
    times = {}
    for i, (t, frame) in enumerate(simulated_frames(paths, args.seed)):
        broker.publish(frame)
        times[frame.frame_id] = t

    def record(frame, result):
        return logger.record_inspection(frame.frame_id, frame.machine, frame.part_type, result.detections,
                                        latency_ms=result.latency_ms, source="stream")

    worker = Worker(broker, FrameProcessor(detect_defects, preprocess_image), StreamMonitor(sinks=[SqliteAlertSink()]),
                    record=record, block_ms=0)
    while worker.step():
        pass

    # the worker stamped rows with the wall clock; put them on the simulated timeline (alerts carry the frame index)
    conn = sqlite3.connect(args.db)
    conn.executemany("UPDATE inspections SET timestamp = ? WHERE id = ?",
                     [(t.strftime("%Y-%m-%d %H:%M:%S"), fid) for fid, t in times.items()])
    by_index = {i: START + timedelta(seconds=STEP_SECONDS * i) for i in range(N_FRAMES)}
    for (idx,) in conn.execute("SELECT DISTINCT frame_index FROM alerts").fetchall():
        conn.execute("UPDATE alerts SET timestamp = ? WHERE frame_index = ?", (by_index[idx].strftime("%Y-%m-%d %H:%M:%S"), idx))
    conn.commit()
    n, d = conn.execute("SELECT COUNT(*), SUM(has_defect) FROM inspections").fetchone()
    print(f"{n} inspections, {d} with a detection; alerts:", conn.execute("SELECT name, status, frame_index, timestamp FROM alerts ORDER BY id").fetchall())
    conn.close()


if __name__ == "__main__":
    main()
