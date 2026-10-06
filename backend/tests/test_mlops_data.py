"""The dashboard numbers must come from logged rows. These tests would have failed against the earlier version, which
returned constants (RAGAS 0.92/0.88/0.95, OEE 89.5, 142 inspections/hour) and a formula-generated hourly chart."""
import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from mlops import logger
from monitoring.alerts import Alert


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(logger.settings, "sqlite_db", str(tmp_path / "t.db"))
    logger._init_db()
    return tmp_path / "t.db"


def metrics():
    return asyncio.run(logger.get_metrics_data())


def insert_at(db, when: datetime, has_defect: bool, latency=None, defect_type="scratches", id_=None):
    con = sqlite3.connect(db)
    con.execute("INSERT INTO inspections (id, timestamp, machine, part_type, has_defect, defect_type, latency_ms, source) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (id_ or f"{when.isoformat()}-{has_defect}-{latency}", when.strftime("%Y-%m-%d %H:%M:%S"), "M1", "strip",
                 has_defect, defect_type if has_defect else "none", latency, "stream"))
    con.commit()
    con.close()


# ---- logging ----------------------------------------------------------------------

def test_record_inspection_is_idempotent_per_id(db):
    det = [{"class_name": "patches", "severity": "low", "confidence": 0.6}, {"class_name": "crazing", "severity": "medium", "confidence": 0.9}]
    assert logger.record_inspection("a", "M1", "strip", det, latency_ms=12.5, source="stream") is True
    assert logger.record_inspection("a", "M1", "strip", det, latency_ms=99.0, source="stream") is False  # redelivery
    row = sqlite3.connect(db).execute("SELECT defect_type, confidence, latency_ms, source, COUNT(*) FROM inspections").fetchone()
    assert row == ("crazing", 0.9, 12.5, "stream", 1)  # the highest-confidence detection is the one recorded


def test_databases_from_older_versions_are_migrated_without_losing_rows(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE inspections (id TEXT PRIMARY KEY, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, machine TEXT, "
                "part_type TEXT, has_defect BOOLEAN, defect_type TEXT, severity TEXT, detections_json TEXT, root_cause TEXT, action_plan_json TEXT)")
    con.execute("INSERT INTO inspections (id, machine, has_defect) VALUES ('old-1', 'M1', 1)")
    con.commit()
    con.close()
    monkeypatch.setattr(logger.settings, "sqlite_db", str(path))
    logger._init_db()
    logger._init_db()  # running it twice is harmless
    cols = {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(inspections)")}
    assert {"latency_ms", "confidence", "source"} <= cols
    assert sqlite3.connect(path).execute("SELECT id, latency_ms FROM inspections").fetchall() == [("old-1", None)]
    assert logger.record_inspection("new-1", "M1", "strip", [], latency_ms=5.0) is True


# ---- dashboard numbers --------------------------------------------------------------

def test_empty_database_reports_zeros_and_no_latency_instead_of_invented_values(db):
    m = metrics()
    assert m["totals"] == {"inspected_today": 0, "defect_rate_pct": 0, "inspections_last_hour": 0, "open_alerts": 0}
    assert m["latency"] == {"n": 0, "p50_ms": None, "p95_ms": None}
    assert len(m["hourly_defects"]) == 24 and all(h["frames"] == 0 and h["count"] == 0 for h in m["hourly_defects"])


def test_nothing_in_the_response_is_a_constant_or_a_metric_the_system_does_not_measure(db):
    m = metrics()
    assert "ragas_scores" not in m and "hourly_oee" not in m and "oee_pct" not in m["totals"]
    assert "inspections_per_hour" not in m["totals"]
    unmeasured = " ".join(x["metric"] for x in m["not_measured"])
    assert "RAGAS" in unmeasured and "OEE" in unmeasured


def test_totals_and_latency_percentiles_are_computed_from_the_rows(db):
    for i, ms in enumerate(range(10, 101, 10)):  # 10 frames now, 4 with a defect
        logger.record_inspection(f"f{i}", "M1", "strip", [{"class_name": "patches", "severity": "low", "confidence": 0.5}] if i < 4 else [],
                                 latency_ms=float(ms))
    m = metrics()
    assert m["totals"]["inspected_today"] == 10 and m["totals"]["defect_rate_pct"] == 40.0
    assert m["totals"]["inspections_last_hour"] == 10
    assert m["latency"] == {"n": 10, "p50_ms": 55.0, "p95_ms": 95.5}
    assert m["defect_distribution"] == [{"name": "patches", "value": 4}]


def test_hourly_buckets_count_real_rows_by_hour_and_drop_rows_older_than_24h(db):
    now = datetime.now(timezone.utc)
    mid = now.replace(minute=30, second=0, microsecond=0)  # rows sit mid-hour, so the test cannot flip across an hour boundary
    insert_at(db, mid - timedelta(hours=2, minutes=-1), True, id_="a")
    insert_at(db, mid - timedelta(hours=2, minutes=-2), False, id_="b")
    insert_at(db, mid - timedelta(hours=5), True, id_="c")
    insert_at(db, now - timedelta(hours=30), True, id_="too-old")
    h = metrics()["hourly_defects"]
    assert len(h) == 24 and h[-1]["hour"] == now.strftime("%H:00")
    assert sum(x["frames"] for x in h) == 3 and sum(x["count"] for x in h) == 2  # the 30-hour-old row is excluded
    assert h[-3] == {"hour": (now - timedelta(hours=2)).strftime("%H:00"), "frames": 2, "count": 1}


# ---- alerts -------------------------------------------------------------------------

def test_open_alerts_are_those_whose_latest_event_is_firing(db):
    logger.log_alert(Alert("defect_rate", "firing", "critical", "too low", 400, details={"lcl": 0.4}))
    logger.log_alert(Alert("drift_brightness", "firing", "warning", "shifted", 410))
    assert {a["name"] for a in logger.get_open_alerts()} == {"defect_rate", "drift_brightness"}
    logger.log_alert(Alert("defect_rate", "resolved", "info", "back within the baseline", 500))
    assert [a["name"] for a in logger.get_open_alerts()] == ["drift_brightness"]
    recent = logger.get_recent_alerts()
    assert [a["status"] for a in recent][0] == "resolved" and recent[-1]["details"] == {"lcl": 0.4}


# ---- API ----------------------------------------------------------------------------

def test_alert_and_stream_endpoints(db, monkeypatch):
    from app import app
    from config import get_settings

    client = TestClient(app)  # no lifespan: no model loading
    logger.log_alert(Alert("stalled", "firing", "critical", "no frame processed for 45 s", 10))
    logger.record_inspection("s1", "M1", "strip", [], latency_ms=8.0, source="stream")

    body = client.get("/api/mlops/alerts").json()
    assert [a["name"] for a in body["open"]] == ["stalled"] and body["recent"][0]["severity"] == "critical"

    monkeypatch.setattr(get_settings(), "redis_url", "")
    status = client.get("/api/stream/status").json()
    assert status["configured"] is False and status["lag"] is None
    assert status["frames_processed"] == 1 and status["open_alerts"] == ["stalled"]

    monkeypatch.setattr(get_settings(), "redis_url", "redis://127.0.0.1:1")  # nothing listens there
    down = client.get("/api/stream/status")
    assert down.status_code == 200 and down.json()["configured"] is True and down.json()["error"]  # API stays up


def test_metrics_endpoint_serves_the_computed_numbers(db):
    from app import app

    logger.record_inspection("x1", "M1", "strip", [], latency_ms=20.0)
    body = TestClient(app).get("/api/mlops/metrics").json()
    assert body["totals"]["inspected_today"] == 1 and body["latency"]["p50_ms"] == 20.0
