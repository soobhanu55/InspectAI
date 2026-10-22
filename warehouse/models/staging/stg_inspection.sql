select
    inspection_id,
    cast(timestamp as timestamp) as ts,
    cast(date_key as integer) as date_key,
    cast(hour as integer) as hour,
    cast(machine_key as integer) as machine_key,
    cast(defect_key as integer) as defect_key,
    cast(has_defect as boolean) as has_defect,
    cast(n_detections as integer) as n_detections,
    confidence,
    latency_ms
from read_csv_auto('{{ var("data_dir") }}/fact_inspection.csv')
