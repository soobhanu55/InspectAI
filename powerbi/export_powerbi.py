"""Exports the inspection log as a star schema for Power BI (CSV files, one per table).

    python powerbi/export_powerbi.py --db backend/fertigungsai.db --out powerbi/data

Tables:  fact_inspection (one row per inspected frame), fact_alert (one row per alert event),
         dim_machine, dim_defect_class, dim_date (calendar), dim_hour.
Keys are plain integers/strings so Power BI can relate them without transformations. Timestamps are UTC.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def read_tables(db_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    conn = sqlite3.connect(db_path)
    try:
        inspections = pd.read_sql_query("SELECT * FROM inspections", conn)
        alerts = pd.read_sql_query("SELECT * FROM alerts", conn)
    finally:
        conn.close()
    return inspections, alerts


def build_star(inspections: pd.DataFrame, alerts: pd.DataFrame) -> dict[str, pd.DataFrame]:
    ins = inspections.copy()
    ins["timestamp"] = pd.to_datetime(ins["timestamp"], utc=True)
    ins["defect_type"] = ins["defect_type"].fillna("none")
    ins["severity"] = ins["severity"].fillna("none")

    dim_machine = (ins[["machine", "part_type"]].drop_duplicates().sort_values(["machine", "part_type"])
                   .reset_index(drop=True).rename_axis("machine_key").reset_index())
    dim_machine["machine_key"] += 1

    classes = sorted(ins["defect_type"].unique(), key=lambda c: (c == "none", c))
    dim_defect = pd.DataFrame({"defect_key": range(1, len(classes) + 1), "defect_class": classes})
    sev = ins.groupby("defect_type")["severity"].agg(lambda s: max(s, key=lambda x: SEVERITY_ORDER.get(x, 0)))
    dim_defect["severity"] = dim_defect["defect_class"].map(sev).fillna("none")

    fact = ins.merge(dim_machine, on=["machine", "part_type"]).merge(
        dim_defect[["defect_key", "defect_class"]], left_on="defect_type", right_on="defect_class")
    fact["n_detections"] = fact["detections_json"].map(lambda j: 0 if not j or j == "[]" else j.count('"class_name"'))
    fact["date_key"] = fact["timestamp"].dt.strftime("%Y%m%d").astype(int)
    fact["hour"] = fact["timestamp"].dt.hour
    fact_inspection = fact[["id", "timestamp", "date_key", "hour", "machine_key", "defect_key", "has_defect",
                            "n_detections", "confidence", "latency_ms", "source"]].rename(columns={"id": "inspection_id"})
    fact_inspection = fact_inspection.assign(has_defect=fact_inspection["has_defect"].astype(int)).sort_values("timestamp")

    days = pd.date_range(ins["timestamp"].min().normalize(), ins["timestamp"].max().normalize(), freq="D")
    dim_date = pd.DataFrame({"date_key": days.strftime("%Y%m%d").astype(int), "date": days.strftime("%Y-%m-%d"),
                             "year": days.year, "month": days.month, "month_name": days.strftime("%B"),
                             "day": days.day, "weekday": days.strftime("%A"), "weekday_number": days.weekday + 1,
                             "is_weekend": (days.weekday >= 5).astype(int)})
    dim_hour = pd.DataFrame({"hour": range(24), "hour_label": [f"{h:02d}:00" for h in range(24)],
                             "shift": ["night"] * 6 + ["early"] * 8 + ["late"] * 8 + ["night"] * 2})

    al = alerts.copy()
    if len(al):
        al["timestamp"] = pd.to_datetime(al["timestamp"], utc=True)
        al["date_key"] = al["timestamp"].dt.strftime("%Y%m%d").astype(int)
        fact_alert = al[["id", "timestamp", "date_key", "name", "status", "severity", "frame_index", "message"]].rename(columns={"id": "alert_id"})
    else:
        fact_alert = pd.DataFrame(columns=["alert_id", "timestamp", "date_key", "name", "status", "severity", "frame_index", "message"])
    return {"fact_inspection": fact_inspection, "fact_alert": fact_alert, "dim_machine": dim_machine,
            "dim_defect_class": dim_defect, "dim_date": dim_date, "dim_hour": dim_hour}


def export(db_path: str, out_dir: str) -> dict[str, int]:
    tables = build_star(*read_tables(db_path))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out / f"{name}.csv", index=False, date_format="%Y-%m-%d %H:%M:%S")
    return {name: len(df) for name, df in tables.items()}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default="powerbi/data")
    args = ap.parse_args()
    for table, n in export(args.db, args.out).items():
        print(f"{table}: {n} rows")
