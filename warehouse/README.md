# InspectAI warehouse (dbt + DuckDB)

The analytics layer over the inspection log: the star-schema CSVs from `powerbi/export_powerbi.py` (one simulated production day through
the real detector, committed in `powerbi/data`) are staged, modelled and tested with dbt on DuckDB (a local file, no server).

```bash
pip install dbt-duckdb
cd warehouse && dbt build --profiles-dir .          # 4 staging views, 3 marts, 20 tests
```

| Layer | Models |
|---|---|
| staging | `stg_inspection`, `stg_alert`, `stg_machine`, `stg_defect_class` |
| marts | `mart_machine_hour` (frames, detection rate, mean confidence, p95 latency), `mart_machine_day` (day total and the blur window), `mart_alert_summary` (events fired and resolved, time span) |
| tests | keys, relationships and accepted values, plus five SQL tests of the data itself |

The SQL tests: a frame is flagged defective exactly when the detector reported a box; confidence is a probability and latency positive;
every machine has frames in all 24 hours; no alert resolves before it fired; and **the simulated lens blur is visible in the numbers**
(M2's detection rate during 14:00-17:00 must be at least 3 points below the rest of the day). The marts reproduce the figures in
`powerbi/README.md` independently of the Python code that wrote them: M2 detects 89.4% of frames during the blur against 97.2% outside it, and the
sharpness-drift alert fires at 14:12:30 and resolves at 17:22:30.
