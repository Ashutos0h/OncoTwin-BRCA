"""FHIR mapping boundary; implement only after agreeing supported codes and units."""
from datetime import datetime, timezone
import uuid

def observation_to_event(observation: dict, twin_id: str) -> dict:
    """
    Maps a FHIR R4 Observation to a ClinicalEvent.
    Supports Tumor Size (LOINC 21889-1), Histologic Grade (LOINC 33732-9), and Nodes (LOINC 21893-3).
    """
    if observation.get("resourceType") != "Observation":
        raise ValueError("Not an Observation")
    
    if observation.get("status") not in ["final", "amended", "corrected"]:
        raise ValueError("Invalid status")

    codes = [c.get("code") for c in observation.get("code", {}).get("coding", [])]
    
    payload = {}
    event_type = "PATHOLOGY_RESULT"
    
    if "21889-1" in codes:
        # Tumor Size
        vq = observation.get("valueQuantity", {})
        unit = vq.get("unit")
        value = vq.get("value")
        if value is None:
            payload["tumour_size_mm"] = None
        else:
            if unit == "cm":
                value = value * 10.0
            elif unit != "mm":
                raise ValueError("Unsupported unit. Only 'mm' and 'cm' are supported for tumor size.")
            if value < 0:
                raise ValueError("Impossible negative value for tumor size")
            payload["tumour_size_mm"] = value
    elif "33732-9" in codes:
        # Histologic Grade
        vq = observation.get("valueQuantity", {})
        value = vq.get("value")
        if value is None:
            payload["grade"] = None
        else:
            if value not in [1, 2, 3, 4]:
                raise ValueError("Grade must be between 1 and 4")
            payload["grade"] = int(value)
    elif "21893-3" in codes:
        # Positive Nodes
        vq = observation.get("valueQuantity", {})
        value = vq.get("value")
        if value is None:
            payload["positive_nodes"] = None
        else:
            if value < 0:
                raise ValueError("Nodes cannot be negative")
            payload["positive_nodes"] = int(value)
    else:
        raise ValueError("Unsupported observation code. Expected 21889-1, 33732-9, or 21893-3.")

    effective_time = observation.get("effectiveDateTime")
    if not effective_time:
        period = observation.get("effectivePeriod", {})
        effective_time = period.get("start") or period.get("end")
    if not effective_time:
        raise ValueError("Missing effectiveDateTime or effectivePeriod")

    obs_id = observation.get("id", str(uuid.uuid4()))
    received_time = observation.get("meta", {}).get("lastUpdated", datetime.now(timezone.utc).isoformat())

    return {
        "schema_version": "0.1.0",
        "twin_id": twin_id,
        "event_id": f"evt_{obs_id}",
        "event_type": event_type,
        "effective_time": effective_time,
        "received_time": received_time,
        "source": "fhir_adapter",
        "quality_status": "valid",
        "provenance": {
            "source_system": "fhir",
            "source_record_id": obs_id,
            "data_version": observation.get("meta", {}).get("versionId", "1")
        },
        "payload": payload
    }
