select
    cast(alert_id as integer) as alert_id,
    cast(timestamp as timestamp) as ts,
    cast(date_key as integer) as date_key,
    name,
    status,
    severity,
    cast(frame_index as integer) as frame_index
from read_csv_auto('{{ var("data_dir") }}/fact_alert.csv')
