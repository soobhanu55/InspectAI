"""MQTT transport and TimescaleDB sink. Unit tests run anywhere; the integration tests at the bottom need a real
Mosquitto (MQTT_URL) and TimescaleDB (TIMESCALE_URL) and are skipped otherwise (CI and docker compose provide both)."""
import io
import os
import struct
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from mlops.timeseries import BUCKETS, TimescaleSink
from monitoring.records import FrameRecord
from streaming import mqtt
from streaming.broker import Frame, InMemoryBroker
from streaming.worker import FrameResult, Worker


def jpeg(color=128, size=96) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(np.full((size, size), color, dtype=np.uint8)).convert("RGB").save(buf, format="JPEG")
    return buf.getvalue()


def frame(i=0, machine="M1") -> Frame:
    return Frame(f"f{i}", machine, "strip", jpeg(), captured_at=1_800_000_000.0 + i, meta={"i": i, "fault": "none"})


# --- codec -----------------------------------------------------------------------------------------------

def test_frame_roundtrips_with_image_bytes_and_metadata_intact():
    sent = frame(7)
    got = mqtt.decode_frame(mqtt.encode_frame(sent))
    assert got == sent


@pytest.mark.parametrize("payload,reason", [
    (b"", "shorter"), (b"\x00\x00", "shorter"), (struct.pack(">I", 0) + b"xx", "does not fit"),
    (struct.pack(">I", 999) + b"{}", "does not fit"), (struct.pack(">I", 2) + b"{}", "bad header"),
    (struct.pack(">I", 3) + b"not", "bad header"),
])
def test_malformed_messages_are_rejected(payload, reason):
    with pytest.raises(mqtt.BadMessage, match=reason):
        mqtt.decode_frame(payload)


def test_oversized_messages_are_rejected():
    with pytest.raises(mqtt.BadMessage, match="too large"):
        mqtt.decode_frame(b"x" * (mqtt.MAX_MESSAGE_BYTES + 1))


def test_topic_follows_the_factory_hierarchy():
    assert mqtt.topic_for(frame(machine="press-3"), "line2") == "factory/line2/press-3/frames"


# --- publisher and bridge (fake client) ---------------------------------------------------------------------

class FakeClient:
    def __init__(self):
        self.published, self.subscribed = [], []

    def publish(self, topic, payload, qos=0):
        self.published.append((topic, payload, qos))
        return SimpleNamespace(mid=len(self.published), wait_for_publish=lambda timeout=None: None)

    def subscribe(self, topic, qos=0):
        self.subscribed.append((topic, qos))


def test_publisher_sends_qos1_to_the_machine_topic():
    client = FakeClient()
    pub = mqtt.MqttFramePublisher(client, line="l1")
    assert pub.publish(frame(1)) == "1"
    topic, payload, qos = client.published[0]
    assert topic == "factory/l1/M1/frames" and qos == 1 and mqtt.decode_frame(payload) == frame(1)
    pub.flush()


def test_bridge_forwards_valid_frames_and_drops_bad_ones():
    broker = InMemoryBroker()
    bridge = mqtt.MqttBridge(broker)
    good = SimpleNamespace(topic="factory/l1/M1/frames", payload=mqtt.encode_frame(frame(2)))
    bad = SimpleNamespace(topic="factory/l1/M1/frames", payload=b"garbage")
    bridge.on_message(None, None, good)
    bridge.on_message(None, None, bad)
    assert dict(bridge.stats) == {"forwarded": 1, "rejected": 1}
    (_, got), = broker.read("c", 10)
    assert got == frame(2)


def test_bridge_resubscribes_on_every_connect():
    client = FakeClient()
    bridge = mqtt.MqttBridge(InMemoryBroker())
    bridge.attach(client)
    client.on_connect(client, None, {}, 0)
    client.on_connect(client, None, {}, 0)  # a broker restart triggers a new connect
    assert client.subscribed == [(mqtt.TOPIC_FILTER, 1)] * 2


# --- worker with a time-series sink ----------------------------------------------------------------------------

class FakeProcessor:
    """Stands in for FrameProcessor: no model and no image decoding. Frames whose image is b"bad" cannot be decoded."""

    def process(self, f):
        if f.image == b"bad":
            raise ValueError("undecodable")
        return FrameResult(f.frame_id, f.machine, [], 12.0, FrameRecord(True, "scratches", 0.9, 100.0, 20.0, 3.0, 12.0))


class RecordingSink:
    def __init__(self, fail=False):
        self.rows, self.fail = [], fail

    def write(self, f, result):
        if self.fail:
            raise ConnectionError("db down")
        self.rows.append((f.frame_id, result.record.has_defect))


def run_worker(frames, sink, record=lambda f, r: True):
    broker = InMemoryBroker()
    for f in frames:
        broker.publish(f)
    w = Worker(broker, FakeProcessor(), None, record=record, block_ms=0, timeseries=sink)
    while w.step():
        pass
    return w, broker


def test_worker_writes_each_processed_frame_to_the_time_series_sink():
    sink = RecordingSink()
    w, _ = run_worker([frame(1), frame(2)], sink)
    assert [r[0] for r in sink.rows] == ["f1", "f2"] and w.stats["ok"] == 2


def test_a_failing_time_series_store_does_not_block_inspection():
    sink = RecordingSink(fail=True)
    w, broker = run_worker([frame(1), frame(2)], sink)
    assert w.stats["ok"] == 2 and w.stats["timeseries_error"] == 2 and broker.lag() == 0


def test_dead_letters_and_duplicates_are_not_written():
    sink = RecordingSink()
    bad = Frame("bad", "M1", "strip", b"bad", captured_at=1.0)
    w, _ = run_worker([bad], sink)
    assert sink.rows == [] and w.stats["dead_letter"] == 1
    sink2 = RecordingSink()
    w2, _ = run_worker([frame(5)], sink2, record=lambda f, r: False)  # already logged: a redelivery
    assert sink2.rows == [] and w2.stats["duplicate"] == 1


# --- sink validation and API --------------------------------------------------------------------------------------

def test_series_rejects_unknown_buckets_and_windows_without_touching_the_database():
    sink = TimescaleSink("postgresql://unused")
    with pytest.raises(ValueError, match="bucket"):
        sink.series(bucket="1 minute; DROP TABLE frame_metrics")
    with pytest.raises(ValueError, match="minutes"):
        sink.series(minutes=0)
    assert "1 minute" in BUCKETS


def test_timeseries_endpoint_reports_unconfigured_and_database_errors(monkeypatch):
    from fastapi.testclient import TestClient

    from app import app
    from config import get_settings

    client = TestClient(app)
    monkeypatch.setattr(get_settings(), "timescale_url", "")
    assert client.get("/api/mlops/timeseries").json() == {"configured": False, "buckets": [], "error": None}
    monkeypatch.setattr(get_settings(), "timescale_url", "postgresql://postgres:x@127.0.0.1:1/none")
    body = client.get("/api/mlops/timeseries").json()
    assert body["configured"] is True and body["buckets"] == [] and body["error"] == "OperationalError"
    assert client.get("/api/mlops/timeseries", params={"bucket": "1 fortnight"}).status_code == 422


# --- integration: real Mosquitto and TimescaleDB -------------------------------------------------------------------------

needs_mqtt = pytest.mark.skipif(not os.environ.get("MQTT_URL"), reason="set MQTT_URL to run against a real MQTT broker")
needs_ts = pytest.mark.skipif(not os.environ.get("TIMESCALE_URL"), reason="set TIMESCALE_URL to run against TimescaleDB")


@needs_mqtt
def test_frames_travel_camera_to_mosquitto_to_bridge_to_stream():
    url = os.environ["MQTT_URL"]
    broker = InMemoryBroker()
    bridge = mqtt.MqttBridge(broker)
    sub = mqtt.new_client(f"test-bridge-{os.urandom(3).hex()}")
    bridge.attach(sub)
    mqtt.connect(sub, url)
    sub.loop_start()
    time.sleep(1.0)  # let the subscription settle
    cam = mqtt.new_client(f"test-camera-{os.urandom(3).hex()}")
    mqtt.connect(cam, url)
    cam.loop_start()
    pub = mqtt.MqttFramePublisher(cam, line=f"t{os.urandom(2).hex()}")
    sent = [frame(i) for i in range(20)]
    for f in sent:
        pub.publish(f)
    pub.flush()
    deadline = time.time() + 10
    while bridge.stats["forwarded"] < 20 and time.time() < deadline:
        time.sleep(0.1)
    cam.loop_stop(), sub.loop_stop()
    cam.disconnect(), sub.disconnect()
    got = [f for _, f in broker.read("c", 100)]
    assert [f.frame_id for f in got] == [f.frame_id for f in sent] and got[0].image == sent[0].image


@pytest.fixture
def sink():
    s = TimescaleSink(os.environ["TIMESCALE_URL"])
    s.ensure_schema()
    with s._connection().cursor() as cur:
        cur.execute("TRUNCATE frame_metrics")
    yield s
    s.close()


def result(defect=True, latency=12.0, sharp=3.0):
    return SimpleNamespace(record=FrameRecord(defect, "scratches" if defect else None, 0.9 if defect else 0.0, 100.0, 20.0, sharp, latency))


@needs_ts
def test_schema_is_a_hypertable_with_a_continuous_aggregate_and_retention(sink):
    sink.ensure_schema()  # idempotent
    with sink._connection().cursor() as cur:
        cur.execute("SELECT count(*) FROM timescaledb_information.hypertables WHERE hypertable_name = 'frame_metrics'")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM timescaledb_information.continuous_aggregates WHERE view_name = 'frame_metrics_1m'")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM timescaledb_information.jobs WHERE hypertable_name = 'frame_metrics' AND proc_name = 'policy_retention'")
        assert cur.fetchone()[0] == 1


@needs_ts
def test_writes_are_idempotent_and_series_aggregates_per_bucket(sink):
    now = time.time()
    frames = [Frame(f"a{i}", "M1", "strip", b"", captured_at=now - 30 + i) for i in range(10)]
    for i, f in enumerate(frames):
        assert sink.write(f, result(defect=i < 3, latency=10.0 + i)) is True
    assert sink.write(frames[0], result()) is False  # redelivery of the same frame is not stored twice
    other = Frame("b0", "M2", "strip", b"", captured_at=now - 5)
    sink.write(other, result(defect=False))
    rows = sink.series(machine="M1", minutes=5, bucket="1 hour")
    assert sum(r["frames"] for r in rows) == 10 and sum(r["defects"] for r in rows) == 3
    assert all(0 <= r["defect_rate"] <= 1 and r["p95_latency_ms"] >= r["avg_latency_ms"] for r in rows)
    assert sum(r["frames"] for r in sink.series(minutes=5, bucket="1 hour")) == 11  # all machines


@needs_ts
def test_worker_to_timescale_end_to_end(sink):
    frames = [Frame(f"e{i}", "M1", "strip", b"", captured_at=time.time() - 5 + i * 0.1) for i in range(15)]
    w, _ = run_worker(frames, sink)
    assert w.stats["ok"] == 15 and w.stats["timeseries_error"] == 0
    assert sum(r["frames"] for r in sink.series(minutes=5, bucket="1 hour")) == 15
