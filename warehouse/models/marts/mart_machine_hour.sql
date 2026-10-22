-- one row per machine and hour: volume, detection rate, confidence and latency (the view behind the quality dashboard)
select
    m.machine,
    i.hour,
    count(*) as frames,
    avg(i.has_defect::int) as detection_rate,
    avg(i.confidence) as mean_confidence,
    quantile_cont(i.latency_ms, 0.95) as p95_latency_ms
from {{ ref('stg_inspection') }} i
join {{ ref('stg_machine') }} m using (machine_key)
group by 1, 2
