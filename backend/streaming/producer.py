"""Simulated camera: replays a folder of images into the stream at a fixed rate, optionally injecting a fault
part-way through so the monitoring can be exercised.

    python -m streaming.producer --source ../data/test/images --count 600 --rate 10 \\
        --fault blur --fault-after 300

Faults: blur (out-of-focus lens), dark (lights failing), noise (sensor noise), or none.
"""
from __future__ import annotations

import argparse
import io
import os
import random
import time
import uuid
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from streaming.broker import Broker, Frame

FAULTS = ("none", "blur", "dark", "noise")


def apply_fault(image: Image.Image, kind: str, rng: np.random.Generator | None = None) -> Image.Image:
    if kind == "none":
        return image
    if kind == "blur":
        return image.filter(ImageFilter.GaussianBlur(3))
    if kind == "dark":
        return ImageEnhance.Brightness(image).enhance(0.5)
    if kind == "noise":
        rng = rng or np.random.default_rng()
        arr = np.asarray(image.convert("RGB"), dtype=np.float64) + rng.normal(0, 25, (image.height, image.width, 3))
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    raise ValueError(f"unknown fault {kind!r}, expected one of {FAULTS}")


def to_jpeg(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def make_frames(paths: list[Path], count: int, machine: str = "M1", part_type: str = "steel-strip", fault: str = "none",
                fault_after: int | None = None, seed: int = 0, clock=time.time):
    """Yield `count` frames sampled with replacement from `paths`; from frame `fault_after` on, the fault is applied."""
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    for i in range(count):
        path = rng.choice(paths)
        faulty = fault != "none" and fault_after is not None and i >= fault_after
        image = apply_fault(Image.open(path), fault, np_rng) if faulty else None
        yield Frame(frame_id=f"{machine}-{uuid.uuid4().hex[:12]}", machine=machine, part_type=part_type,
                    image=to_jpeg(image) if image is not None else path.read_bytes(), captured_at=clock(),
                    meta={"index": i, "source": path.name, "fault": fault if faulty else "none"})


def publish_stream(broker: Broker, frames, rate_hz: float = 0.0, sleep=time.sleep) -> int:
    n = 0
    for frame in frames:
        broker.publish(frame)
        n += 1
        if rate_hz > 0:
            sleep(1 / rate_hz)
    return n


def main() -> None:  # pragma: no cover - CLI wiring
    import redis

    from streaming.broker import RedisStreamBroker

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="folder of .jpg/.png/.bmp images to replay")
    ap.add_argument("--count", type=int, default=600)
    ap.add_argument("--rate", type=float, default=10.0, help="frames per second (0 = as fast as possible)")
    ap.add_argument("--machine", default="M1")
    ap.add_argument("--fault", choices=FAULTS, default="none")
    ap.add_argument("--fault-after", type=int, default=None, help="frame index at which the fault starts")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--transport", choices=("redis", "mqtt"), default="redis",
                    help="redis: write the stream directly; mqtt: publish like a camera gateway (MQTT_URL), a bridge forwards to Redis")
    args = ap.parse_args()

    paths = sorted(p for p in Path(args.source).iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"})
    if args.transport == "mqtt":
        from streaming.mqtt import MqttFramePublisher, connect, new_client

        client = new_client(f"camera-{args.machine}")
        connect(client, os.environ.get("MQTT_URL", "mqtt://localhost:1883"))
        client.loop_start()
        broker = MqttFramePublisher(client)
    else:
        broker = RedisStreamBroker(redis.Redis.from_url(os.environ["REDIS_URL"]))
    n = publish_stream(broker, make_frames(paths, args.count, args.machine, fault=args.fault,
                                           fault_after=args.fault_after, seed=args.seed), args.rate)
    if args.transport == "mqtt":
        broker.flush()  # QoS 1 publishes are acknowledged asynchronously: wait for the last one
        client.loop_stop()
        client.disconnect()
    print(f"published {n} frames")


if __name__ == "__main__":  # pragma: no cover
    main()
