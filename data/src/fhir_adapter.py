"""FHIR mapping boundary; implement only after agreeing supported codes and units."""
from datetime import datetime, timezone
import uuid

def observation_to_event(observation: dict, twin_id: str) -> dict:
    """
    Maps a FHIR R4 Observation to a ClinicalEvent.
    Supports only Tumor Size (LOINC 21889-1) for now.
    """
    if observation.get("resourceType") != "Observation":
        raise ValueError("Not an Observation")
    
    if observation.get("status") not in ["final", "amended", "corrected"]:
        raise ValueError("Invalid status")

    # Check code
    codes = [c.get("code") for c in observation.get("code", {}).get("coding", [])]
    if "21889-1" not in codes:
        raise ValueError("Unsupported observation code. Only LOINC 21889-1 (Tumor Size) is supported.")
    
    # Check units
    vq = observation.get("valueQuantity", {})
    if vq.get("unit") != "mm":
        raise ValueError("Unsupported unit. Only 'mm' is supported.")
    
    value = vq.get("value")
    if value is None or value < 0:
        raise ValueError("Impossible or missing value for tumor size")

    effective_time = observation.get("effectiveDateTime")
    if not effective_time:
        raise ValueError("Missing effectiveDateTime")

    obs_id = observation.get("id", str(uuid.uuid4()))
    
    # Received time could be meta.lastUpdated or now
    received_time = observation.get("meta", {}).get("lastUpdated", datetime.now(timezone.utc).isoformat())

    return {
        "schema_version": "0.1.0",
        "twin_id": twin_id,
        "event_id": f"evt_{obs_id}",
        "event_type": "PATHOLOGY_RESULT",
        "effective_time": effective_time,
        "received_time": received_time,
        "source": "fhir_adapter",
        "quality_status": "valid",
        "provenance": {
            "source_system": "fhir",
            "source_record_id": obs_id,
            "data_version": observation.get("meta", {}).get("versionId", "1")
        },
        "payload": {
            "tumour_size_mm": value
        }
    }
