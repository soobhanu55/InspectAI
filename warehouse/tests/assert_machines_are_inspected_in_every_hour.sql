-- the sample is one continuous day: every machine has frames in all 24 hours
select machine, count(distinct hour) as hours
from {{ ref('mart_machine_hour') }}
group by 1
having count(distinct hour) <> 24
