"""Pieces the Kubernetes deployment relies on: synthetic camera frames and waiting for the database at start-up.
Also checks the manifests statically (every image, probe and policy the pipeline needs is declared)."""
import io
from pathlib import Path

import pytest
import yaml
from PIL import Image

from mlops.timeseries import ensure_schema_with_retry
from streaming.mqtt import decode_frame, encode_frame
from streaming.producer import make_synthetic_frames

K8S = Path(__file__).resolve().parents[2] / "deploy" / "k8s"


def test_synthetic_frames_are_decodable_distinct_and_survive_the_mqtt_codec():
    frames = list(make_synthetic_frames(5, machine="M7", seed=3))
    assert len(frames) == 5 and len({f.frame_id for f in frames}) == 5 and len({f.image for f in frames}) == 5
    assert all(f.machine == "M7" and f.meta["source"] == "synthetic" for f in frames)
    assert Image.open(io.BytesIO(frames[0].image)).size == (200, 200)
    assert decode_frame(encode_frame(frames[0])) == frames[0]


class FlakySink:
    def __init__(self, failures):
        self.failures, self.calls = failures, 0

    def ensure_schema(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError("database starting")


def test_worker_waits_for_the_database_then_proceeds():
    sleeps = []
    sink = FlakySink(3)
    ensure_schema_with_retry(sink, attempts=10, delay=2.0, sleep=sleeps.append)
    assert sink.calls == 4 and sleeps == [2.0, 2.0, 2.0]


def test_worker_gives_up_after_the_last_attempt():
    with pytest.raises(ConnectionError):
        ensure_schema_with_retry(FlakySink(99), attempts=3, delay=0, sleep=lambda s: None)


def docs(path):
    return [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d]


def base_resources():
    return [d for f in sorted((K8S / "base").glob("*.yaml")) if f.name != "kustomization.yaml" for d in docs(f)]


def test_every_long_running_workload_has_probes_requests_and_a_memory_limit():
    workloads = [d for d in base_resources() if d["kind"] in ("Deployment", "StatefulSet")]
    assert {d["metadata"]["name"] for d in workloads} == {"redis", "mosquitto", "timescaledb", "backend", "stream-worker", "mqtt-bridge"}
    for d in workloads:
        c = d["spec"]["template"]["spec"]["containers"][0]
        assert c["resources"]["requests"] and "memory" in c["resources"]["limits"], d["metadata"]["name"]
        if d["metadata"]["name"] != "mqtt-bridge":  # the bridge has no port to probe
            assert "readinessProbe" in c and "livenessProbe" in c, d["metadata"]["name"]


def test_the_database_password_is_never_in_the_repository():
    text = "\n".join(p.read_text(encoding="utf-8") for p in (K8S / "base").glob("*.yaml"))
    assert "kind: Secret" not in text and "secretKeyRef" in text
    ci = (K8S / "overlays" / "ci" / "kustomization.yaml").read_text(encoding="utf-8")
    assert "not-a-secret" in ci  # the CI overlay's throwaway value is labelled as such


def test_network_policies_cover_every_backing_service():
    policies = [d for d in base_resources() if d["kind"] == "NetworkPolicy"]
    selected = {tuple(sorted((p["spec"]["podSelector"].get("matchLabels") or {}).items())) for p in policies}
    for app in ("redis", "mosquitto", "timescaledb"):
        assert (("app", app),) in selected
    assert any(p["spec"]["podSelector"] == {} and p["spec"]["policyTypes"] == ["Ingress"] for p in policies)  # default deny


def test_the_worker_is_pinned_to_the_api_node_because_they_share_a_sqlite_volume():
    worker = next(d for d in base_resources() if d["metadata"]["name"] == "stream-worker" and d["kind"] == "Deployment")
    terms = worker["spec"]["template"]["spec"]["affinity"]["podAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]
    assert terms[0]["labelSelector"]["matchLabels"] == {"app": "backend"}
