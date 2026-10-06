"""The Power BI export builds a consistent star schema from the inspection log."""
import importlib.util
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def exporter():
    spec = importlib.util.spec_from_file_location("export_powerbi", ROOT / "powerbi" / "export_powerbi.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "log.db"
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE inspections (id TEXT PRIMARY KEY, timestamp TEXT, machine TEXT, part_type TEXT, has_defect INT,
                    defect_type TEXT, severity TEXT, detections_json TEXT, root_cause TEXT, action_plan_json TEXT,
                    latency_ms REAL, confidence REAL, source TEXT)""")
    conn.execute("""CREATE TABLE alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, name TEXT, status TEXT, severity TEXT,
                    message TEXT, frame_index INT, details_json TEXT)""")
    rows = [
        ("a", "2026-09-01 00:10:00", "M1", "strip", 1, "scratches", "medium", '[{"class_name": "scratches"}, {"class_name": "scratches"}]', 12.0, 0.9, "stream"),
        ("b", "2026-09-01 14:05:00", "M2", "strip", 0, None, None, "[]", 14.0, None, "stream"),
        ("c", "2026-09-02 23:59:00", "M2", "strip", 1, "crazing", "low", '[{"class_name": "crazing"}]', 11.0, 0.7, "api"),
    ]
    conn.executemany("INSERT INTO inspections (id, timestamp, machine, part_type, has_defect, defect_type, severity, detections_json, latency_ms, confidence, source) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.execute("INSERT INTO alerts (timestamp, name, status, severity, message, frame_index) VALUES ('2026-09-01 14:30:00', 'hit_rate_shift', 'firing', 'warning', 'm', 10)")
    conn.commit()
    conn.close()
    return str(path)


def test_star_schema_keys_resolve(exporter, db):
    t = exporter.build_star(*exporter.read_tables(db))
    f = t["fact_inspection"]
    assert len(f) == 3 and f["inspection_id"].is_unique
    assert set(f["machine_key"]) <= set(t["dim_machine"]["machine_key"])
    assert set(f["defect_key"]) <= set(t["dim_defect_class"]["defect_key"])
    assert set(f["date_key"]) <= set(t["dim_date"]["date_key"]) and set(f["hour"]) <= set(t["dim_hour"]["hour"])
    assert set(t["fact_alert"]["date_key"]) <= set(t["dim_date"]["date_key"])


def test_measures_inputs_are_correct(exporter, db):
    f = exporter.build_star(*exporter.read_tables(db))["fact_inspection"].set_index("inspection_id")
    assert f.loc["a", "n_detections"] == 2 and f.loc["b", "n_detections"] == 0 and f.loc["c", "n_detections"] == 1
    assert list(f["has_defect"]) == [1, 0, 1] and f.loc["a", "date_key"] == 20260901 and f.loc["b", "hour"] == 14


def test_no_defect_frames_get_the_none_class_last(exporter, db):
    d = exporter.build_star(*exporter.read_tables(db))["dim_defect_class"]
    assert list(d["defect_class"]) == ["crazing", "scratches", "none"] and d.loc[d["defect_class"] == "none", "severity"].item() == "none"


def test_date_dimension_is_a_complete_calendar(exporter, db):
    d = exporter.build_star(*exporter.read_tables(db))["dim_date"]
    assert list(d["date_key"]) == [20260901, 20260902] and d["weekday"].tolist() == ["Tuesday", "Wednesday"]


def test_hour_dimension_assigns_every_hour_to_a_shift(exporter, db):
    h = exporter.build_star(*exporter.read_tables(db))["dim_hour"]
    assert len(h) == 24 and h["shift"].value_counts().to_dict() == {"early": 8, "late": 8, "night": 8}


def test_export_writes_one_csv_per_table(exporter, db, tmp_path):
    counts = exporter.export(db, str(tmp_path / "out"))
    assert set(counts) == {"fact_inspection", "fact_alert", "dim_machine", "dim_defect_class", "dim_date", "dim_hour"}
    assert pd.read_csv(tmp_path / "out" / "fact_inspection.csv").shape[0] == 3


def test_empty_alert_table_still_exports(exporter, db):
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()
    assert len(exporter.build_star(*exporter.read_tables(db))["fact_alert"]) == 0
