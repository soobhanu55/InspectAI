"""SQLite log of inspections and alerts, and the dashboard numbers computed from it.

Every figure returned by get_metrics_data() is computed from the logged rows. Nothing is a constant: earlier versions
returned fixed RAGAS scores, OEE and throughput and a formula-generated hourly chart; those were removed because
this system measures none of them (see "not_measured" in the response). The API process and the stream worker both
write to this file, hence WAL mode and a busy timeout.
"""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import numpy as np

from config import get_settings

settings = get_settings()

NEW_INSPECTION_COLUMNS = {"latency_ms": "REAL", "confidence": "REAL", "source": "TEXT DEFAULT 'api'"}


def _get_db():
    conn = sqlite3.connect(settings.sqlite_db, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db():
    conn = _get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS inspections (
            id TEXT PRIMARY KEY,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            machine TEXT,
            part_type TEXT,
            has_defect BOOLEAN,
            defect_type TEXT,
            severity TEXT,
            detections_json TEXT,
            root_cause TEXT,
            action_plan_json TEXT
        )
    ''')
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(inspections)")}
    for column, ddl in NEW_INSPECTION_COLUMNS.items():  # databases created by older versions get the new columns
        if column not in existing:
            conn.execute(f"ALTER TABLE inspections ADD COLUMN {column} {ddl}")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            name TEXT, status TEXT, severity TEXT, message TEXT, frame_index INTEGER, details_json TEXT
        )
    ''')
    conn.commit()
    conn.close()


# Initialize DB on import
_init_db()


def record_inspection(inspection_id: str, machine: str, part_type: str, detections: list, result: dict | None = None,
                      latency_ms: float | None = None, source: str = "api") -> bool:
    """Insert one inspection; returns False if this id was already logged (a redelivered stream frame)."""
    result = result or {}
    has_defect = len(detections) > 0
    top = max(detections, key=lambda d: d["confidence"]) if has_defect else None
    conn = _get_db()
    cur = conn.execute('''
        INSERT OR IGNORE INTO inspections
        (id, machine, part_type, has_defect, defect_type, severity, detections_json, root_cause, action_plan_json,
         latency_ms, confidence, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        inspection_id, machine, part_type, has_defect,
        top["class_name"] if top else "none", top["severity"] if top else "none",
        json.dumps(detections), result.get("root_cause", ""), json.dumps(result.get("action_plan", [])),
        latency_ms, top["confidence"] if top else None, source,
    ))
    conn.commit()
    inserted = cur.rowcount == 1
    conn.close()
    return inserted


async def log_inspection(inspection_id: str, machine: str, part_type: str, detections: list, result: dict,
                         latency_ms: float | None = None):
    record_inspection(inspection_id, machine, part_type, detections, result, latency_ms, source="api")


def log_alert(alert) -> None:
    conn = _get_db()
    conn.execute("INSERT INTO alerts (timestamp, name, status, severity, message, frame_index, details_json) VALUES (?,?,?,?,?,?,?)",
                 (alert.timestamp.replace("T", " ").replace("+00:00", ""), alert.name, alert.status, alert.severity,
                  alert.message, alert.frame_index, json.dumps(alert.details)))
    conn.commit()
    conn.close()


async def get_recent_inspections(limit: int = 50):
    conn = _get_db()
    rows = conn.execute('SELECT * FROM inspections ORDER BY timestamp DESC LIMIT ?', (limit,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_recent_alerts(limit: int = 50) -> list[dict]:
    conn = _get_db()
    rows = conn.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    out = []
    for row in rows:
        d = dict(row)
        d["details"] = json.loads(d.pop("details_json") or "{}")
        out.append(d)
    return out


def get_open_alerts() -> list[dict]:
    """Alerts whose most recent event is 'firing' (not yet resolved)."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT a.* FROM alerts a
        JOIN (SELECT name, MAX(id) AS last_id FROM alerts GROUP BY name) l ON a.id = l.last_id
        WHERE a.status = 'firing'
        ORDER BY a.id DESC
    """).fetchall()
    conn.close()
    return [{k: v for k, v in dict(r).items() if k != "details_json"} for r in rows]


def stream_summary() -> dict:
    """What the stream worker has processed so far, from the log."""
    conn = _get_db()
    count, last = conn.execute("SELECT COUNT(*), MAX(timestamp) FROM inspections WHERE source = 'stream'").fetchone()
    conn.close()
    return {"frames_processed": count, "last_frame_at": last, "open_alerts": [a["name"] for a in get_open_alerts()]}


NOT_MEASURED = [
    {"metric": "RAGAS faithfulness / answer relevancy / context precision",
     "reason": "backend/mlops/evaluation.py is an empty placeholder; RAG answers are not scored automatically"},
    {"metric": "OEE",
     "reason": "needs machine uptime, planned production time and good-part counts, which this system does not collect"},
]


async def get_metrics_data():
    conn = _get_db()
    now = datetime.now(timezone.utc)

    today = conn.execute("SELECT COUNT(*), COALESCE(SUM(has_defect), 0) FROM inspections WHERE date(timestamp) = date('now')").fetchone()
    inspected_today, defects_today = today[0], int(today[1])
    last_hour = conn.execute("SELECT COUNT(*) FROM inspections WHERE timestamp >= datetime('now', '-1 hour')").fetchone()[0]

    dist_rows = conn.execute("SELECT defect_type, COUNT(*) AS count FROM inspections WHERE has_defect = 1 GROUP BY defect_type").fetchall()

    # Real hourly buckets for the last 24 hours (UTC), empty hours included
    hourly_rows = conn.execute("""
        SELECT strftime('%Y-%m-%d %H', timestamp) AS h, COUNT(*) AS frames, COALESCE(SUM(has_defect), 0) AS defects
        FROM inspections WHERE timestamp >= datetime('now', '-24 hours') GROUP BY h
    """).fetchall()
    by_hour = {r["h"]: (r["frames"], int(r["defects"])) for r in hourly_rows}
    hourly = []
    for back in range(23, -1, -1):
        t = now - timedelta(hours=back)
        frames, defects = by_hour.get(t.strftime("%Y-%m-%d %H"), (0, 0))
        hourly.append({"hour": t.strftime("%H:00"), "frames": frames, "count": defects})

    lat = [r[0] for r in conn.execute("SELECT latency_ms FROM inspections WHERE latency_ms IS NOT NULL ORDER BY timestamp DESC LIMIT 1000")]
    conn.close()

    return {
        "hourly_defects": hourly,
        "defect_distribution": [{"name": r["defect_type"], "value": r["count"]} for r in dist_rows],
        "latency": {"n": len(lat), "p50_ms": round(float(np.percentile(lat, 50)), 1) if lat else None,
                    "p95_ms": round(float(np.percentile(lat, 95)), 1) if lat else None},
        "totals": {
            "inspected_today": inspected_today,
            "defect_rate_pct": round(100 * defects_today / inspected_today, 1) if inspected_today else 0,
            "inspections_last_hour": last_hour,
            "open_alerts": len(get_open_alerts()),
        },
        "alerts": get_recent_alerts(10),
        "not_measured": NOT_MEASURED,
    }
