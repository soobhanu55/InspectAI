-- one row per machine: the whole day, and the blur window the committed sample simulates (M2, 14:00 to 17:00)
select
    m.machine,
    count(*) as frames,
    avg(i.has_defect::int) as detection_rate,
    avg(case when i.hour between 14 and 16 then i.has_defect::int end) as detection_rate_14_to_17,
    avg(case when i.hour not between 14 and 16 then i.has_defect::int end) as detection_rate_outside_14_to_17
from {{ ref('stg_inspection') }} i
join {{ ref('stg_machine') }} m using (machine_key)
group by 1
