VITALS_THRESHOLDS = {
    "pr": {
        "label": "Pulse Rate",
        "short_label": "PR",
        "unit": "bpm",
        "green": {"min": 60, "max": 100},
        "orange": [{"lt": 60}, {"gt": 100}],
        "red": [{"lt": 50}, {"gt": 110}],
        "display_min": 40,
        "display_max": 140,
    },
    "spo2": {
        "label": "SpO2",
        "short_label": "SpO2",
        "unit": "%",
        "green": {"gte": 96},
        "orange": [{"gte": 92, "lt": 96}],
        "red": [{"lt": 92}],
        "display_min": 80,
        "display_max": 100,
    },
    "hemoglobin": {
        "label": "Hemoglobin",
        "short_label": "Hb",
        "unit": "g/dL",
        "green": {"gte": 11},
        "orange": [{"gte": 10, "lt": 11}],
        "red": [{"lt": 10}],
        "display_min": 4,
        "display_max": 16,
    },
    "blood_pressure": {
        "label": "Blood Pressure",
        "short_label": "BP",
        "unit": "mmHg",
        "green": {"systolic_lt": 120, "diastolic_lt": 80},
        "orange": [{"systolic_gte": 120}, {"diastolic_gte": 80}],
        "red": [{"systolic_gte": 140}, {"diastolic_gte": 90}],
        "display_min": {"systolic": 70, "diastolic": 40},
        "display_max": {"systolic": 180, "diastolic": 120},
    },
    "weight": {
        "label": "Weight",
        "short_label": "Wt",
        "unit": "kg",
        "status": "neutral",
        "display_min": 30,
        "display_max": 120,
    },
}

VITALS_STATUS_LABELS = {
    "blood_pressure": {
        "green": "Normal",
        "orange": "Elevated",
        "red": "High",
        "na": "No pair",
    },
    "pr": {
        "green": "Normal",
        "orange": "Mild",
        "red": "Extreme",
        "na": "N/A",
    },
    "spo2": {
        "green": "Normal",
        "orange": "Mild",
        "red": "Extreme",
        "na": "N/A",
    },
    "hemoglobin": {
        "green": "Normal",
        "orange": "Mild anemia",
        "red": "Moderate / severe",
        "na": "N/A",
    },
    "weight": {
        "neutral": "Tracked",
        "na": "N/A",
    },
}


def vitals_metric_status(metric_key, value):
    if value is None:
        return "na"
    if metric_key == "weight":
        return "neutral"

    numeric_value = float(value)
    if metric_key == "pr":
        if numeric_value < 50 or numeric_value > 110:
            return "red"
        if numeric_value < 60 or numeric_value > 100:
            return "orange"
        return "green"
    if metric_key == "spo2":
        if numeric_value < 92:
            return "red"
        if numeric_value < 96:
            return "orange"
        return "green"
    if metric_key == "hemoglobin":
        if numeric_value < 10:
            return "red"
        if numeric_value < 11:
            return "orange"
        return "green"
    return "na"


def vitals_metric_status_label(metric_key, status):
    return VITALS_STATUS_LABELS.get(metric_key, {}).get(status, "N/A")


def blood_pressure_status(systolic, diastolic):
    if systolic is None and diastolic is None:
        return "na"
    if (systolic is not None and float(systolic) >= 140) or (diastolic is not None and float(diastolic) >= 90):
        return "red"
    if (systolic is not None and float(systolic) >= 120) or (diastolic is not None and float(diastolic) >= 80):
        return "orange"
    return "green"


def vitals_thresholds_payload():
    return {
        "version": 1,
        "metrics": VITALS_THRESHOLDS,
        "status_labels": VITALS_STATUS_LABELS,
    }
