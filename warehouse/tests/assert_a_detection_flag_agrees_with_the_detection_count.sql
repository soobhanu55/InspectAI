-- has_defect must be true exactly when the detector reported at least one box
select * from {{ ref('stg_inspection') }}
where has_defect <> (n_detections > 0)
