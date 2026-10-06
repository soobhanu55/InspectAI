"""Per-frame inspection metrics in TimescaleDB (PostgreSQL with time-series extensions).

SQLite remains the system of record for inspections and alerts; this sink adds what a time-series database is for:
a hypertable partitioned by time, a continuous aggregate (per-minute defect counts and latency per machine that the
database keeps up to date), and a retention policy. It is optional: the worker only uses it when TIMESCALE_URL is set,
and a failing database never blocks inspection (see Worker).

    TIMESCALE_URL=postgresql://postgres:postgres@localhost:5432/inspect
"""
from __future__ import annotations

import time

import structlog

logger = structlog.get_logger()

BUCKETS = ("10 seconds", "1 minute", "5 minutes", "1 hour")  # allow-list: the bucket width is interpolated as an interval

SCHEMA = [
    "CREATE EXTENSION IF NOT EXISTS timescaledb",
    """CREATE TABLE IF NOT EXISTS frame_metrics (
        time timestamptz NOT NULL, machine text NOT NULL, part_type text, frame_id text NOT NULL,
        has_defect boolean NOT NULL, top_class text, confidence real, brightness real, contrast real,
        sharpness real, latency_ms real)""",
    "SELECT create_hypertable('frame_metrics', 'time', if_not_exists => TRUE)",
    # a redelivered frame must not be counted twice; a unique index on a hypertable has to include the time column
    "CREATE UNIQUE INDEX IF NOT EXISTS frame_metrics_frame_uq ON frame_metrics (frame_id, time)",
    "CREATE INDEX IF NOT EXISTS frame_metrics_machine_time ON frame_metrics (machine, time DESC)",
    """CREATE MATERIALIZED VIEW IF NOT EXISTS frame_metrics_1m WITH (timescaledb.continuous) AS
       SELECT time_bucket('1 minute', time) AS bucket, machine, count(*) AS frames, sum(has_defect::int) AS defects,
              avg(latency_ms) AS avg_latency_ms, avg(sharpness) AS avg_sharpness
       FROM frame_metrics GROUP BY bucket, machine WITH NO DATA""",
    """SELECT add_continuous_aggregate_policy('frame_metrics_1m', start_offset => INTERVAL '1 day',
       end_offset => INTERVAL '1 minute', schedule_interval => INTERVAL '1 minute', if_not_exists => TRUE)""",
    "SELECT add_retention_policy('frame_metrics', INTERVAL '30 days', if_not_exists => TRUE)",
]

INSERT = """INSERT INTO frame_metrics (time, machine, part_type, frame_id, has_defect, top_class, confidence,
            brightness, contrast, sharpness, latency_ms)
            VALUES (to_timestamp(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING"""

SERIES = """SELECT time_bucket(%(bucket)s::interval, time) AS bucket, count(*) AS frames, sum(has_defect::int) AS defects,
            avg(latency_ms) AS avg_latency_ms, percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
            avg(sharpness) AS avg_sharpness
            FROM frame_metrics WHERE time > now() - %(window)s::interval AND (%(machine)s::text IS NULL OR machine = %(machine)s)
            GROUP BY bucket ORDER BY bucket"""


class TimescaleSink:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self._conn = None

    def _connection(self):
        import psycopg2

        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.dsn, connect_timeout=5)
            self._conn.autocommit = True  # continuous aggregates cannot be created inside a transaction block
        return self._conn

    def ensure_schema(self) -> None:
        with self._connection().cursor() as cur:
            for statement in SCHEMA:
                cur.execute(statement)

    def write(self, frame, result) -> bool:
        """Insert one frame's metrics. Returns False if that frame was already stored."""
        r = result.record
        with self._connection().cursor() as cur:
            cur.execute(INSERT, (frame.captured_at, frame.machine, frame.part_type, frame.frame_id, r.has_defect,
                                 r.top_class, r.confidence, r.brightness, r.contrast, r.sharpness, r.latency_ms))
            return cur.rowcount == 1

    def series(self, machine: str | None = None, minutes: int = 60, bucket: str = "1 minute") -> list[dict]:
        if bucket not in BUCKETS:
            raise ValueError(f"bucket must be one of {BUCKETS}")
        if not 1 <= minutes <= 60 * 24 * 30:
            raise ValueError("minutes must be between 1 and 43200")
        with self._connection().cursor() as cur:
            cur.execute(SERIES, {"bucket": bucket, "window": f"{minutes} minutes", "machine": machine})
            rows = cur.fetchall()
        return [{"bucket": b.isoformat(), "frames": int(n), "defects": int(d), "defect_rate": round(int(d) / int(n), 4),
                 "avg_latency_ms": round(float(lat), 2), "p95_latency_ms": round(float(p95), 2),
                 "avg_sharpness": round(float(sh), 2)} for b, n, d, lat, p95, sh in rows]

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()


def query_series(dsn: str, machine: str | None, minutes: int, bucket: str) -> list[dict]:
    """One-shot query for the API: open, query, close."""
    sink = TimescaleSink(dsn)
    try:
        return sink.series(machine, minutes, bucket)
    finally:
        sink.close()


def ensure_schema_with_retry(sink: TimescaleSink, attempts: int = 30, delay: float = 2.0, sleep=time.sleep) -> None:
    """Create the schema, waiting for the database to come up (in Kubernetes the worker can start before it is ready)."""
    for attempt in range(1, attempts + 1):
        try:
            sink.ensure_schema()
            return
        except Exception as exc:
            if attempt == attempts:
                raise
            logger.warning("timescale_not_ready", attempt=attempt, error=type(exc).__name__)
            sleep(delay)
