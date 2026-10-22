select cast(machine_key as integer) as machine_key, machine, part_type
from read_csv_auto('{{ var("data_dir") }}/dim_machine.csv')
