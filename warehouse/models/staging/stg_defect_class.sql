select cast(defect_key as integer) as defect_key, defect_class, severity
from read_csv_auto('{{ var("data_dir") }}/dim_defect_class.csv')
