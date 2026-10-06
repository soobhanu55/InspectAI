import json

import httpx
import numpy as np
import pytest
from PIL import Image, ImageFilter

from monitoring.alerts import Alert, MemorySink, WebhookSink
from monitoring.detectors import Breach, ClassMixDrift, FeatureDrift, HitRateShift, LatencySLO
from monitoring.features import image_stats
from monitoring.monitor import StreamMonitor
from monitoring.records import FrameRecord

CLASSES = ["crazing", "inclusion", "patches", "pitted_surface", "rolled-in_scale", "scratches"]


def rec(defect=True, cls="patches", conf=0.7, brightness=100.0, contrast=30.0, sharpness=50.0, latency=20.0):
    return FrameRecord(defect, cls if defect else None, conf if defect else 0.0, brightness, contrast, sharpness, latency)


def stream(n, rng, defect_rate=0.5, shift=0.0):
    """n in-control (or shifted-brightness) records with noisy image statistics and a uniform class mix."""
    return [rec(bool(rng.random() < defect_rate), cls=str(rng.choice(CLASSES)), conf=float(rng.uniform(0.3, 0.9)),
                brightness=float(rng.normal(100 + shift, 5)), contrast=float(rng.normal(30, 3)),
                sharpness=float(rng.normal(50, 5)), latency=float(rng.normal(20, 2))) for _ in range(n)]


# ---- image features ------------------------------------------------------------

def test_image_stats_on_flat_images():
    b, c, s = image_stats(Image.new("L", (32, 32), 200))
    assert (b, c, s) == (200.0, 0.0, 0.0)  # no contrast, no edges


def test_blur_lowers_sharpness_but_not_brightness():
    rng = np.random.default_rng(0)
    img = Image.fromarray(rng.integers(0, 256, (64, 64), dtype=np.uint8))
    sharp, blurred = image_stats(img), image_stats(img.filter(ImageFilter.GaussianBlur(3)))
    assert blurred[2] < sharp[2] * 0.2 and abs(blurred[0] - sharp[0]) < 5


# ---- detectors ----------------------------------------------------------------

def test_hit_rate_shift_up_and_down_with_directional_messages():
    d = HitRateShift()
    d.fit([rec(True)] * 50 + [rec(False)] * 50)
    assert d.check([rec(True)] * 50 + [rec(False)] * 50) is None
    up = d.check([rec(True)] * 85 + [rec(False)] * 15)
    assert up.severity == "critical" and "above" in up.message and up.details["p_value"] < 1e-4
    down = d.check([rec(True)] * 15 + [rec(False)] * 85)
    assert "below" in down.message and "camera" in down.message


def test_hit_rate_shift_does_not_false_alarm_when_the_hit_rate_is_near_100_percent():
    """The failure that motivated the exact test: at a 97% hit rate, 7 misses in a window of 100 (vs ~3 expected) is ordinary
    luck, but control limits of mean +/- 3.5 sigma flagged windows like it on real detector output."""
    d = HitRateShift()
    d.fit([rec(True)] * 146 + [rec(False)] * 4)  # 97.3%
    assert d.check([rec(True)] * 93 + [rec(False)] * 7) is None
    assert d.check([rec(True)] * 90 + [rec(False)] * 10) is None
    assert d.check([rec(True)] * 70 + [rec(False)] * 30) is not None  # a real collapse is still caught


def test_hit_rate_shift_handles_a_baseline_with_no_defects_and_one_with_all():
    none, allhit = HitRateShift(), HitRateShift()
    none.fit([rec(False)] * 100)
    allhit.fit([rec(True)] * 100)
    assert none.check([rec(False)] * 100) is None and none.check([rec(True)] * 30 + [rec(False)] * 70) is not None
    assert allhit.check([rec(True)] * 100) is None and allhit.check([rec(True)] * 60 + [rec(False)] * 40) is not None


def test_a_short_baseline_gives_wider_tolerance_than_a_long_one():
    """With 20 frames the baseline rate is barely known, so a modest difference is not evidence; with 400 it is."""
    short, long_ = HitRateShift(), HitRateShift()
    short.fit([rec(True)] * 10 + [rec(False)] * 10)
    long_.fit([rec(True)] * 200 + [rec(False)] * 200)
    w = [rec(True)] * 75 + [rec(False)] * 25
    assert short.check(w) is None and long_.check(w) is not None


def test_class_mix_drift_flags_a_dominant_class_but_not_the_same_mix():
    base = [rec(cls=c) for c in CLASSES for _ in range(30)]
    d = ClassMixDrift()
    d.fit(base)
    assert d.check([rec(cls=c) for c in CLASSES for _ in range(20)]) is None
    shifted = d.check([rec(cls="scratches")] * 100)
    assert shifted is not None and "scratches" in shifted.message
    assert d.check([rec(cls="patches")] * 10) is None  # too few defects to say anything
    assert d.check([rec(cls="never-seen")] * 100) is not None  # a class absent from the baseline


def test_feature_drift_ks():
    rng = np.random.default_rng(1)
    d = FeatureDrift("drift_brightness", lambda r: r.brightness)
    d.fit(stream(150, rng))
    assert d.check(stream(100, rng)) is None
    breach = d.check(stream(100, rng, shift=20))
    assert breach is not None and breach.details["window_median"] > breach.details["baseline_median"] + 10
    assert d.check(stream(10, rng, shift=20)) is None  # window too small


def test_confidence_drift_only_looks_at_defective_frames():
    d = FeatureDrift("drift_confidence", lambda r: r.confidence, only_defects=True)
    d.fit([rec(conf=0.8)] * 60 + [rec(defect=False)] * 60)
    assert d.check([rec(defect=False)] * 100) is None  # no defective frames: nothing to compare
    assert d.check([rec(conf=0.3)] * 40 + [rec(defect=False)] * 60) is not None


def test_latency_slo_relative_and_fixed_limits():
    base = [rec(latency=float(x)) for x in range(1, 101)]  # p95 = 95.05
    rel = LatencySLO(factor=2.0)
    rel.fit(base)
    assert rel.limit == pytest.approx(190.1, rel=1e-3)
    assert rel.check([rec(latency=100.0)] * 100) is None
    assert rel.check([rec(latency=300.0)] * 100) is not None
    fixed = LatencySLO(limit_ms=50)
    fixed.fit(base)
    assert fixed.limit == 50 and fixed.check([rec(latency=60.0)] * 100) is not None


# ---- monitor -----------------------------------------------------------------

class Scheduled:
    """Test detector: breaches exactly on the listed check numbers."""

    name = "scheduled"

    def __init__(self, breach_on):
        self.breach_on, self.calls = set(breach_on), 0

    def fit(self, baseline):
        pass

    def check(self, window):
        self.calls += 1
        return Breach(self.name, "test breach", "warning") if self.calls in self.breach_on else None


def drive(monitor, n):
    out = []
    for _ in range(n):
        out += monitor.observe(rec())
    return out


def mon(detector, **kw):
    kw = {"baseline_frames": 10, "window": 10, "check_every": 5, "consecutive": 2, **kw}
    return StreamMonitor(detectors=[detector], **kw)


def test_no_alerts_while_the_baseline_is_collected():
    det = Scheduled(breach_on=range(1, 99))
    assert drive(mon(det), 10) == [] and det.calls == 0


def test_one_noisy_window_does_not_fire_but_two_in_a_row_do():
    m = mon(Scheduled(breach_on={1, 3, 4}))  # breach, clear, breach, breach
    alerts = drive(m, 35)
    assert [(a.name, a.status) for a in alerts] == [("scheduled", "firing")]
    # checks run at frames 20, 25, 30, 35 (the window of 10 must fill first); breach, clear, breach, breach -> fires at 35
    assert alerts[0].frame_index == 35


def test_firing_alert_is_not_repeated_and_resolves_after_consecutive_clean_checks():
    m = mon(Scheduled(breach_on={1, 2, 3, 4}))  # 4 breaches then clean
    alerts = drive(m, 10 + 8 * 5)
    assert [a.status for a in alerts] == ["firing", "resolved"]
    assert m.status()["firing"] == []


def test_in_control_stream_raises_no_alert_with_the_default_detectors():
    rng = np.random.default_rng(7)
    m = StreamMonitor()
    assert all(m.observe(r) == [] for r in stream(900, rng))


def test_brightness_shift_fires_a_drift_alert_soon_after_the_change_and_not_before():
    rng = np.random.default_rng(3)
    m = StreamMonitor()
    fired = []
    for i, r in enumerate(stream(300, rng) + stream(300, rng, shift=25), start=1):
        fired += [(i, a.name) for a in m.observe(r) if a.status == "firing"]
    assert fired and all(i > 300 for i, _ in fired)
    assert ("drift_brightness" in {n for _, n in fired}) and min(i for i, _ in fired) <= 300 + 100 + 20


def test_stall_fires_once_and_resolves_when_frames_resume():
    now = [0.0]
    m = StreamMonitor(detectors=[], stall_seconds=30, clock=lambda: now[0], baseline_frames=1)
    assert m.check_stall() is None  # nothing seen yet: not a stall
    m.observe(rec())
    now[0] = 29
    assert m.check_stall() is None
    now[0] = 31
    alert = m.check_stall()
    assert alert.name == "stalled" and alert.severity == "critical" and m.check_stall() is None
    now[0] = 40
    resolved = m.observe(rec())
    assert [(a.name, a.status) for a in resolved] == [("stalled", "resolved")]


# ---- sinks --------------------------------------------------------------------

def test_a_failing_sink_does_not_stop_the_stream_or_other_sinks():
    class Broken:
        def emit(self, alert):
            raise RuntimeError("disk full")

    good = MemorySink()
    m = StreamMonitor(sinks=[Broken(), good], detectors=[Scheduled({1, 2})], baseline_frames=10, window=10, check_every=5)
    drive(m, 25)  # checks at frames 20 and 25 both breach
    assert [a.status for a in good.alerts] == ["firing"]


def test_webhook_posts_the_alert_text_and_counts_failures_without_raising():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200)

    sink = WebhookSink("https://hooks.example/test", client=httpx.Client(transport=httpx.MockTransport(handler)))
    sink.emit(Alert("defect_rate", "firing", "critical", "rate too high", 500))
    assert seen[0]["text"].startswith("[CRITICAL] defect_rate firing") and sink.failures == 0

    bad = WebhookSink("https://hooks.example/test", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    bad.emit(Alert("x", "firing", "warning", "m", 1))
    assert bad.failures == 1
