-- the sample simulates a blurred lens on M2 from 14:00 to 17:00; the detection rate there must be clearly lower than the rest of the day
select machine, detection_rate_14_to_17, detection_rate_outside_14_to_17
from {{ ref('mart_machine_day') }}
where machine = 'M2' and detection_rate_14_to_17 > detection_rate_outside_14_to_17 - 0.03
