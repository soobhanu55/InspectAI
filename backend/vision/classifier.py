# Severity map is in detector.py
def classify_severity(defect_type: str) -> str:
    from vision.detector import SEVERITY_MAP
    return SEVERITY_MAP.get(defect_type, "low")
