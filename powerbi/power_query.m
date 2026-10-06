// Power Query (M) for loading the exported CSVs. In Power BI Desktop: Home > Transform data > New source > Blank query,
// open the Advanced Editor and paste ONE query per table (adjust DataFolder once, then reference it).

// ---- Parameter query named DataFolder (type Text) ----
// "C:\path\to\InspectAI\powerbi\data"

// ---- fact_inspection ----
let
    Source = Csv.Document(File.Contents(DataFolder & "\fact_inspection.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"inspection_id", type text}, {"timestamp", type datetime}, {"date_key", Int64.Type}, {"hour", Int64.Type},
        {"machine_key", Int64.Type}, {"defect_key", Int64.Type}, {"has_defect", Int64.Type}, {"n_detections", Int64.Type},
        {"confidence", type number}, {"latency_ms", type number}, {"source", type text}}, "en-US")
in
    Typed

// ---- fact_alert ----
let
    Source = Csv.Document(File.Contents(DataFolder & "\fact_alert.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"alert_id", Int64.Type}, {"timestamp", type datetime}, {"date_key", Int64.Type}, {"name", type text},
        {"status", type text}, {"severity", type text}, {"frame_index", Int64.Type}, {"message", type text}}, "en-US")
in
    Typed

// ---- dimensions (same pattern; only the column types differ) ----
// dim_machine:      machine_key Int64, machine text, part_type text
// dim_defect_class: defect_key Int64, defect_class text, severity text   (sort defect_class by defect_key)
// dim_date:         date_key Int64, date date, year Int64, month Int64, month_name text, day Int64, weekday text,
//                   weekday_number Int64, is_weekend Int64   (sort month_name by month, weekday by weekday_number)
// dim_hour:         hour Int64, hour_label text, shift text   (sort hour_label by hour)
let
    Source = Csv.Document(File.Contents(DataFolder & "\dim_hour.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{"hour", Int64.Type}, {"hour_label", type text}, {"shift", type text}}, "en-US")
in
    Typed
