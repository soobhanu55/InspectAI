-- an alert that fired must not have resolved before its first firing
select name, first_fired_at, last_resolved_at
from {{ ref('mart_alert_summary') }}
where last_resolved_at is not null and last_resolved_at < first_fired_at
