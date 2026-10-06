# Power BI report: InspectAI quality dashboard

I cannot produce a `.pbix` file (Power BI Desktop is a Windows GUI application). This folder holds everything that goes into one: the star schema as CSV
files, the Power Query loaders, the DAX measures, a theme, and a page-by-page build guide. Building it takes about 30 minutes in Power BI Desktop (free).

```bash
# real use: export your own inspection log
python powerbi/export_powerbi.py --db backend/inspectai.db --out powerbi/data
# the committed sample: one simulated production day through the real detector and monitor
python powerbi/make_sample_day.py --images /path/to/NEU-DET/test/images --db /tmp/day.db     # run from backend/
python powerbi/export_powerbi.py --db /tmp/day.db --out powerbi/data
```

## The sample data, honestly

5,760 frames over one simulated day (2026-09-01), two machines alternating, one frame every 15 seconds. From 14:00 to 17:00 machine M2's lens is blurred. The
detections, latencies and alerts come from the real fine-tuned YOLO and the real stream monitor; **only the clock is simulated**, and the images are re-sampled
NEU-DET test images, so the defect mix is that dataset's, not a factory's. What it shows: the detection rate on M2 drops from 97.2% to 89.4% during the blur,
and the monitor's sharpness alert fires at 14:12:30 (12.5 minutes after the lens went out of focus) and resolves at 17:22:30; the latency alerts come from a few
slow frames (maximum 2.2 s, GPU and model warm-up).

## Data model (star schema)

| Table | Grain | Key columns |
|---|---|---|
| `fact_inspection` | one row per inspected frame | `inspection_id`, `timestamp`, `date_key`, `hour`, `machine_key`, `defect_key`, `has_defect`, `n_detections`, `confidence`, `latency_ms` |
| `fact_alert` | one row per alert event (firing or resolved) | `alert_id`, `timestamp`, `date_key`, `name`, `status`, `severity`, `frame_index` |
| `dim_machine` | machine and part type | `machine_key`, `machine`, `part_type` |
| `dim_defect_class` | defect classes plus "none" | `defect_key`, `defect_class`, `severity` |
| `dim_date`, `dim_hour` | calendar and hour of day (with shift) | `date_key`; `hour`, `hour_label`, `shift` |

Relationships (all many-to-one, single direction): `fact_inspection[date_key]` and `fact_alert[date_key]` to `dim_date`; `fact_inspection[hour]` to `dim_hour`; `fact_inspection[machine_key]` to `dim_machine`;
`fact_inspection[defect_key]` to `dim_defect_class`. Mark `dim_date` as the date table; sort `month_name` by `month`, `weekday` by `weekday_number`, `hour_label` by `hour`, `defect_class` by `defect_key`.

## Steps

1. **Load**: create a text parameter `DataFolder` pointing at `powerbi/data`, then paste the queries from `power_query.m` (one per table; the dimensions follow the same pattern, their column types are listed in the file).
2. **Model**: add the relationships above.
3. **Measures**: paste `measures.dax` into a new `_Measures` table. Each measure is commented, including the one caveat that matters: the classic p-chart limits are unreliable when the rate is near 100%, so the page uses the real monitor's alerts as the markers.
4. **Pages**
   - *Overview*: cards for `Inspections`, `Detection Rate`, `P95 Latency ms`, `Open Alerts`; line chart of `Detection Rate` by `dim_hour[hour_label]` with `Detection Rate At Alert` as markers; slicers for machine and date.
   - *Machines*: matrix of `dim_machine[machine]` by `dim_hour[hour_label]` showing `Detection Rate` with a colour scale (the M2 blur window stands out); a column chart of `Detection Rate vs Day` by machine.
   - *Defect classes*: donut of `Defect Share` by `defect_class`, stacked column of `Detections` by hour and class.
   - *Alerts*: table of `fact_alert` (timestamp, name, status, severity), `Alerts Fired` and `Alert Minutes Firing` by `name`, a timeline of alert events.
5. **Theme**: View > Themes > Browse for themes > `theme.json`.

## Limits

One simulated day; the "defect" share reflects a research dataset in which every part has a defect; `Latency Budget ms` is an assumed value; `Alert Minutes Firing` assumes one firing/resolved pair per alert name in the current filter context (several pairs per day are summed by first firing to last resolved, which overstates the time with several episodes).
