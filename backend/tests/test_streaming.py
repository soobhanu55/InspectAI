import io
import os

import numpy as np
import pytest
from PIL import Image

from monitoring.alerts import MemorySink
from monitoring.monitor import StreamMonitor
from monitoring.features import image_stats
from streaming.broker import Frame, InMemoryBroker, RedisStreamBroker
from streaming.producer import apply_fault, make_frames, publish_stream
from streaming.worker import FrameProcessor, Worker


def jpeg(color=128, size=96, texture=False) -> bytes:
    rng = np.random.default_rng(0)
    arr = rng.integers(0, 256, (size, size), dtype=np.uint8) if texture else np.full((size, size), color, dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).convert("RGB").save(buf, format="JPEG")
    return buf.getvalue()


def frame(i=0, **kw) -> Frame:
    return Frame(f"f{i}", "M1", "strip", jpeg(), captured_at=1000.0 + i, meta={"i": i}, **kw)


# ---- broker: the same contract for every implementation -----------------------------

@pytest.fixture(params=["memory", "fakeredis", "redis"])
def make_broker(request):
    if request.param == "memory":
        return lambda **kw: InMemoryBroker(**kw)
    if request.param == "fakeredis":
        import fakeredis

        server = fakeredis.FakeServer()
        return lambda **kw: RedisStreamBroker(fakeredis.FakeRedis(server=server), stream=f"s-{id(kw)}-{os.urandom(3).hex()}", **kw)
    if not os.environ.get("REDIS_URL"):
        pytest.skip("set REDIS_URL to also run against a real Redis")
    import redis

    client = redis.Redis.from_url(os.environ["REDIS_URL"])
    return lambda **kw: RedisStreamBroker(client, stream=f"test-{os.urandom(4).hex()}", **kw)


def test_frames_roundtrip_with_bytes_and_metadata_intact(make_broker):
    b = make_broker()
    sent = frame(3)
    b.publish(sent)
    (entry_id, got), = b.read("w1", count=5, block_ms=50)
    assert (got.frame_id, got.machine, got.part_type, got.image, got.captured_at, got.meta) == \
           (sent.frame_id, sent.machine, sent.part_type, sent.image, sent.captured_at, sent.meta)


def test_each_frame_goes_to_exactly_one_consumer(make_broker):
    b = make_broker()
    for i in range(10):
        b.publish(frame(i))
    a = [f.frame_id for _, f in b.read("w1", count=6, block_ms=50)]
    c = [f.frame_id for _, f in b.read("w2", count=6, block_ms=50)]
    assert sorted(a + c) == sorted(f"f{i}" for i in range(10)) and not set(a) & set(c)


def test_lag_counts_unread_and_unacknowledged_frames(make_broker):
    b = make_broker()
    for i in range(5):
        b.publish(frame(i))
    assert b.lag() == 5
    got = b.read("w1", count=3, block_ms=50)
    assert b.lag() == 5  # 3 delivered but not acknowledged + 2 waiting
    for entry_id, _ in got:
        b.ack(entry_id)
    assert b.lag() == 2


def test_unacknowledged_frames_can_be_taken_over_by_another_consumer(make_broker):
    b = make_broker()
    for i in range(2):
        b.publish(frame(i))
    b.read("crashed-worker", count=2, block_ms=50)  # read, then "crash" without acknowledging
    taken = b.reclaim("w2", min_idle_ms=0)
    assert sorted(f.frame_id for _, f in taken) == ["f0", "f1"]
    for entry_id, _ in taken:
        b.ack(entry_id)
    assert b.lag() == 0


def test_the_stream_is_capped_and_drops_the_oldest_frames(make_broker):
    b = make_broker(maxlen=3)
    for i in range(5):
        b.publish(frame(i))
    assert [f.frame_id for _, f in b.read("w1", count=10, block_ms=50)] == ["f2", "f3", "f4"]


def test_reclaim_respects_the_idle_time():
    now = [0.0]
    b = InMemoryBroker(clock=lambda: now[0])
    b.publish(frame(0))
    b.read("w1", count=1)
    assert b.reclaim("w2", min_idle_ms=30_000) == []
    now[0] = 31
    assert len(b.reclaim("w2", min_idle_ms=30_000)) == 1


# ---- worker -----------------------------------------------------------------------

def fake_detect(image):
    return [{"class_name": "scratches", "confidence": 0.8, "severity": "medium", "bbox": {}}]


def preprocess(raw: bytes):
    return Image.open(io.BytesIO(raw)).convert("RGB")


class Recorder:
    def __init__(self, seen=None):
        self.rows, self.seen = [], seen if seen is not None else set()

    def __call__(self, frame, result):
        if frame.frame_id in self.seen:
            return False
        self.seen.add(frame.frame_id)
        self.rows.append((frame.frame_id, len(result.detections), result.latency_ms))
        return True


class Metrics:
    def __init__(self):
        self.calls = {"frame": [], "alert": [], "lag": [], "processed": 0, "delay": []}

    def queue_delay(self, s): self.calls["delay"].append(s)
    def frame(self, status): self.calls["frame"].append(status)
    def lag(self, n): self.calls["lag"].append(n)
    def defect_rate(self, machine, rate): self.calls["rate"] = (machine, rate)
    def alert(self, a): self.calls["alert"].append(a.name)
    def processed(self, r): self.calls["processed"] += 1


def worker(broker, detect=fake_detect, monitor=None, recorder=None, metrics=None, **kw):
    return Worker(broker, FrameProcessor(detect, preprocess), monitor, record=recorder, metrics=metrics, block_ms=0, **kw)


def test_worker_processes_logs_measures_and_acknowledges():
    b, rec, m = InMemoryBroker(), Recorder(), Metrics()
    for i in range(3):
        b.publish(frame(i))
    w = worker(b, recorder=rec, metrics=m, monitor=StreamMonitor(detectors=[], baseline_frames=1))
    assert w.step() == 3
    assert [r[0] for r in rec.rows] == ["f0", "f1", "f2"] and all(r[1] == 1 and r[2] > 0 for r in rec.rows)
    assert b.lag() == 0 and w.stats["ok"] == 3 and w.monitor.frames_seen == 3
    assert m.calls["frame"] == ["ok"] * 3 and m.calls["processed"] == 3 and m.calls["rate"] == ("M1", 1.0)


def test_an_undecodable_frame_is_dead_lettered_and_acknowledged_not_retried_forever():
    b, rec = InMemoryBroker(), Recorder()
    b.publish(Frame("bad", "M1", "strip", b"this is not an image"))
    b.publish(frame(1))
    w = worker(b, recorder=rec)
    w.step()
    assert w.stats["dead_letter"] == 1 and w.stats["ok"] == 1 and b.lag() == 0
    assert [r[0] for r in rec.rows] == ["f1"]  # the bad frame did not block the good one


def test_a_crash_while_detecting_leaves_the_frame_unacknowledged_for_retry():
    now = [0.0]
    b, rec = InMemoryBroker(clock=lambda: now[0]), Recorder()
    b.publish(frame(0))
    calls = {"n": 0}

    def flaky(image):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("CUDA out of memory")
        return fake_detect(image)

    w = worker(b, detect=flaky, recorder=rec, reclaim_idle_ms=30_000)
    w.step()
    assert w.stats["error"] == 1 and b.lag() == 1 and rec.rows == []  # not acknowledged, not logged
    now[0] = 31
    w.step()  # the stream is idle, so the worker reclaims the abandoned frame
    assert w.stats["ok"] == 1 and b.lag() == 0 and [r[0] for r in rec.rows] == ["f0"]


def test_a_redelivered_frame_is_not_counted_twice():
    b, rec = InMemoryBroker(), Recorder(seen={"f0"})  # f0 was already logged before the redelivery
    b.publish(frame(0))
    monitor = StreamMonitor(detectors=[], baseline_frames=1)
    w = worker(b, recorder=rec, monitor=monitor)
    w.step()
    assert w.stats["duplicate"] == 1 and w.stats["ok"] == 0 and b.lag() == 0
    assert monitor.frames_seen == 0 and rec.rows == []


def test_an_idle_worker_raises_the_stall_alert_through_the_monitor():
    now = [0.0]
    sink = MemorySink()
    monitor = StreamMonitor(sinks=[sink], detectors=[], baseline_frames=1, stall_seconds=30, clock=lambda: now[0])
    b = InMemoryBroker()
    b.publish(frame(0))
    m = Metrics()
    w = worker(b, monitor=monitor, metrics=m)
    w.step()
    now[0] = 45
    assert w.step() == 0  # idle: nothing to read, nothing to reclaim
    assert [a.name for a in sink.alerts] == ["stalled"] and m.calls["alert"] == ["stalled"]


def test_the_processor_reduces_a_frame_to_a_monitor_record():
    proc = FrameProcessor(fake_detect, preprocess)
    flat = proc.process(Frame("a", "M1", "s", jpeg(color=200))).record
    assert flat.has_defect and flat.top_class == "scratches" and flat.confidence == 0.8
    assert flat.brightness == pytest.approx(200, abs=2) and flat.contrast < 2 and flat.sharpness < 5
    none = FrameProcessor(lambda im: [], preprocess).process(Frame("b", "M1", "s", jpeg())).record
    assert not none.has_defect and none.top_class is None and none.confidence == 0.0


# ---- producer ---------------------------------------------------------------------

def test_faults_change_the_image_statistics_in_the_expected_direction():
    rng = np.random.default_rng(0)
    base = Image.fromarray(rng.integers(60, 200, (96, 96), dtype=np.uint8)).convert("RGB")
    b0, c0, s0 = image_stats(base)
    assert image_stats(apply_fault(base, "blur"))[2] < s0 * 0.3
    assert image_stats(apply_fault(base, "dark"))[0] < b0 * 0.6
    assert image_stats(apply_fault(base, "noise", np.random.default_rng(1)))[2] > s0
    assert apply_fault(base, "none") is base
    with pytest.raises(ValueError):
        apply_fault(base, "melt")


def test_make_frames_is_reproducible_and_flags_the_fault_from_the_right_frame(tmp_path):
    paths = []
    for i in range(3):
        p = tmp_path / f"img{i}.jpg"
        p.write_bytes(jpeg(texture=True))
        paths.append(p)
    a = list(make_frames(paths, 6, fault="blur", fault_after=4, seed=5, clock=lambda: 1.0))
    b = list(make_frames(paths, 6, fault="blur", fault_after=4, seed=5, clock=lambda: 1.0))
    assert [f.meta for f in a] == [f.meta for f in b]
    assert [f.meta["fault"] for f in a] == ["none"] * 4 + ["blur"] * 2
    assert a[0].image == paths[[p.name for p in paths].index(a[0].meta["source"])].read_bytes()  # clean frames are sent untouched


def test_publish_stream_paces_frames_at_the_requested_rate():
    sleeps = []
    b = InMemoryBroker()
    n = publish_stream(b, (frame(i) for i in range(4)), rate_hz=10, sleep=sleeps.append)
    assert n == 4 and b.lag() == 4 and sleeps == [0.1] * 4
