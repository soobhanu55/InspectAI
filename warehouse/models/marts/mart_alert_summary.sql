-- firing and resolved events per alert, and the time from the first firing to the last resolution
select
    name,
    max(severity) as severity,
    sum(case when status = 'firing' then 1 else 0 end) as fired,
    sum(case when status = 'resolved' then 1 else 0 end) as resolved,
    min(case when status = 'firing' then ts end) as first_fired_at,
    max(case when status = 'resolved' then ts end) as last_resolved_at,
    date_diff('minute', min(case when status = 'firing' then ts end), max(case when status = 'resolved' then ts end)) as minutes_first_fire_to_last_resolve
from {{ ref('stg_alert') }}
group by 1
