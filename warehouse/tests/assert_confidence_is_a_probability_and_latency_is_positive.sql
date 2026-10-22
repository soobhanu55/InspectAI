select * from {{ ref('stg_inspection') }}
where confidence < 0 or confidence > 1 or latency_ms <= 0 or hour not between 0 and 23
