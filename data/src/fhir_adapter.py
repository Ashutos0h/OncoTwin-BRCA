"""
FHIR R4 → ClinicalEvent adapter for OncoTwin-BRCA.

Supported LOINC Observation codes
----------------------------------
Pathology observations (event_type=PATHOLOGY_RESULT):
  21889-1  Tumor size (mm or cm → stored as mm)
  33732-9  Histologic grade (1–4; Nottingham 1–3 + Grade 4 undifferentiated/anaplastic)
  21893-3  Regional lymph nodes positive (count ≥ 0)

Biomarker observations (event_type=BIOMARKER_RESULT):
  85319-2  HER2 Ag [Presence] in Breast cancer.IHC (supports positive/negative/equivocal,
           ordinal scores '0', '1+', '2+', '3+', and numeric score 0–3)
  85337-4  ER [Presence] in Breast cancer.IHC (supports positive/negative, % staining)
  85347-3  PR [Presence] in Breast cancer.IHC (supports positive/negative, % staining)
  59847-4  Ki-67 nuclear antigen [Labeling index] in Tissue (%)

Diagnosis observations (event_type=DIAGNOSIS):
  29308-4  Diagnosis (morphology, coded via valueCodeableConcept.coding[0])

Compound / Multi-measurement Observations
-----------------------------------------
Supports FHIR Observation.component[] arrays (e.g. Receptor Status panels or
Pathology panels), mapping each component to its respective payload field.

Provenance fields
-----------------
  source_system    : "fhir"
  source_record_id : Observation.id (or UUID if absent)
  data_version     : Observation.meta.versionId (or "1")

quality_status is set to "valid" for complete records, "warning" when any
payload field is None (missing/partial), and invalid records raise ValueError.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Feature dictionary (agreed with ML lead; do not change keys without review)
# ---------------------------------------------------------------------------
FEATURE_DICT: dict[str, str] = {
    "tumour_size_mm":  "Largest tumour dimension in millimetres (float, ≥ 0)",
    "grade":           "Histologic grade (int, 1–4: 1–3 Nottingham, 4 undifferentiated)",
    "positive_nodes":  "Number of regional lymph nodes with tumour (int, ≥ 0)",
    "her2_status":     "HER2 IHC result: 'positive' | 'negative' | 'equivocal' | null",
    "er_status":       "Oestrogen receptor IHC result: 'positive' | 'negative' | null",
    "pr_status":       "Progesterone receptor IHC result: 'positive' | 'negative' | null",
    "ki67_percent":    "Ki-67 proliferation index as percentage (float, 0–100)",
    "morphology_code": "ICD-O-3 morphology code string (e.g. '8500/3')",
}

# ---------------------------------------------------------------------------
# LOINC code → field registry
# ---------------------------------------------------------------------------
_PATHOLOGY_CODES: dict[str, str] = {
    "21889-1": "tumour_size_mm",
    "33732-9": "grade",
    "21893-3": "positive_nodes",
}
_BIOMARKER_CODES: dict[str, str] = {
    "85319-2": "her2_status",
    "85337-4": "er_status",
    "85347-3": "pr_status",
    "59847-4": "ki67_percent",
}
_DIAGNOSIS_CODES: set[str] = {"29308-4"}

_ALL_SUPPORTED = set(_PATHOLOGY_CODES) | set(_BIOMARKER_CODES) | _DIAGNOSIS_CODES

# Accepted FHIR Observation.status values
_ACCEPTED_STATUSES = {"final", "amended", "corrected"}

# IHC string mappings (normalised to lowercase)
_IHC_SYNONYMS: dict[str, str] = {
    "positive": "positive",
    "pos": "positive",
    "negative": "negative",
    "neg": "negative",
    "equivocal": "equivocal",
    "indeterminate": "equivocal",
    "borderline": "equivocal",
    # Ordinal HER2 scores (ASCO/CAP guidelines)
    "0": "negative",
    "0+": "negative",
    "1+": "negative",
    "1": "negative",
    "2+": "equivocal",
    "2": "equivocal",
    "3+": "positive",
    "3": "positive",
}


def _extract_codes(resource_or_component: dict) -> list[str]:
    """Extract code strings from code.coding list."""
    codings = resource_or_component.get("code", {}).get("coding", [])
    codes: list[str] = []
    for c in codings:
        code_val = c.get("code")
        if code_val:
            codes.append(str(code_val).strip())
    return codes


def _extract_effective_time(observation: dict) -> str:
    t = observation.get("effectiveDateTime")
    if not t:
        period = observation.get("effectivePeriod", {})
        t = period.get("start") or period.get("end")
    if not t:
        raise ValueError("Missing effectiveDateTime or effectivePeriod")
    return str(t)


def _map_tumour_size(vq: dict) -> tuple[float | None, bool]:
    """Returns (value_mm, is_missing)."""
    value = vq.get("value")
    if value is None:
        return None, True
    unit = vq.get("unit", "mm")
    if unit == "cm":
        value = round(value * 10.0, 6)
    elif unit != "mm":
        raise ValueError(
            f"Unsupported unit '{unit}'. Only 'mm' and 'cm' are supported for tumor size."
        )
    if value < 0:
        raise ValueError("Impossible or missing value for tumor size: value must be ≥ 0")
    return float(value), False


def _map_grade(vq: dict) -> tuple[int | None, bool]:
    """Returns (grade_int, is_missing). Supports grades 1-4."""
    value = vq.get("value")
    if value is None:
        return None, True
    try:
        int_val = int(value)
    except (ValueError, TypeError):
        raise ValueError(f"Grade must be an integer between 1 and 4. Got {value}.")
    if int_val not in (1, 2, 3, 4):
        raise ValueError(
            f"Grade must be between 1 and 4 (1-3 Nottingham, 4 undifferentiated). Got {int_val}."
        )
    return int_val, False


def _map_positive_nodes(vq: dict) -> tuple[int | None, bool]:
    """Returns (node_count, is_missing)."""
    value = vq.get("value")
    if value is None:
        return None, True
    try:
        int_val = int(value)
    except (ValueError, TypeError):
        raise ValueError(f"Positive nodes must be an integer ≥ 0. Got {value}.")
    if int_val < 0:
        raise ValueError("Nodes cannot be negative")
    return int_val, False


def _map_ihc_status(container: dict, field: str) -> tuple[str | None, bool]:
    """
    Reads valueCodeableConcept, valueString, or valueQuantity for IHC result.
    Supports qualitative text, ordinal scores ('0', '1+', '2+', '3+'), and
    quantitative values (e.g. HER2 score 0–3, or ER/PR percentage staining).
    """
    # 1. Check valueQuantity (e.g. score 0-3 for HER2, or percentage for ER/PR)
    vq = container.get("valueQuantity")
    if vq and vq.get("value") is not None:
        num_val = float(vq["value"])
        unit = vq.get("unit", "")
        if field == "her2_status":
            if num_val in (0.0, 1.0):
                return "negative", False
            if num_val == 2.0:
                return "equivocal", False
            if num_val == 3.0:
                return "positive", False
            raise ValueError(
                f"Numeric HER2 score must be 0, 1, 2, or 3. Got {num_val}."
            )
        if field in ("er_status", "pr_status"):
            # If percentage given, >= 1% is positive by ASCO/CAP guidelines
            if unit == "%" or (0.0 <= num_val <= 100.0):
                return "positive" if num_val >= 1.0 else "negative", False

    # 2. Check valueCodeableConcept or valueString
    vcc = container.get("valueCodeableConcept", {})
    raw: str | None = vcc.get("text")
    if not raw:
        codings = vcc.get("coding", [])
        raw = codings[0].get("display") if codings else None
    if not raw:
        raw = container.get("valueString")
    if raw is None:
        return None, True

    cleaned = raw.strip().lower()
    # Direct lookup or synonym lookup
    if cleaned in _IHC_SYNONYMS:
        return _IHC_SYNONYMS[cleaned], False

    # Strip surrounding whitespace or plus sign formatting
    match = re.match(r"^([0-3])\+?$", cleaned)
    if match and match.group(0) in _IHC_SYNONYMS:
        return _IHC_SYNONYMS[match.group(0)], False

    raise ValueError(
        f"Unsupported IHC value '{raw}' for {field}. "
        f"Expected one of: positive, negative, equivocal, or scores 0, 1+, 2+, 3+."
    )


def _map_ki67(container: dict) -> tuple[float | None, bool]:
    """Returns (percentage, is_missing)."""
    vq = container.get("valueQuantity", {})
    value = vq.get("value")
    if value is None:
        return None, True
    unit = vq.get("unit", "%")
    if unit != "%":
        raise ValueError(f"Unsupported unit '{unit}' for Ki-67. Expected '%'.")
    pct = float(value)
    if not (0.0 <= pct <= 100.0):
        raise ValueError(f"Impossible Ki-67 value {pct}. Must be in range [0, 100].")
    return pct, False


def _map_morphology(container: dict) -> tuple[str | None, bool]:
    """
    Reads morphology code from valueCodeableConcept.coding.
    Expects ICD-O-3 system (e.g. SNOMED/ICD-O-3 code).
    """
    vcc = container.get("valueCodeableConcept", {})
    codings = vcc.get("coding", [])
    if not codings:
        return None, True
    code_str = codings[0].get("code")
    if not code_str:
        return None, True
    return str(code_str), False


def _extract_field_value(
    code: str, container: dict
) -> tuple[str, Any, bool, str]:
    """
    Maps a single supported code + container to (field_name, value, is_missing, category).
    Category is 'PATHOLOGY', 'BIOMARKER', or 'DIAGNOSIS'.
    """
    if code in _PATHOLOGY_CODES:
        field = _PATHOLOGY_CODES[code]
        category = "PATHOLOGY"
        vq = container.get("valueQuantity", {})
        if code == "21889-1":
            val, missing = _map_tumour_size(vq)
        elif code == "33732-9":
            val, missing = _map_grade(vq)
        else:  # 21893-3
            val, missing = _map_positive_nodes(vq)
        return field, val, missing, category

    if code in _BIOMARKER_CODES:
        field = _BIOMARKER_CODES[code]
        category = "BIOMARKER"
        if code == "59847-4":
            val, missing = _map_ki67(container)
        else:
            val, missing = _map_ihc_status(container, field)
        return field, val, missing, category

    if code in _DIAGNOSIS_CODES:
        field = "morphology_code"
        category = "DIAGNOSIS"
        val, missing = _map_morphology(container)
        return field, val, missing, category

    raise ValueError(f"Unrecognised code '{code}'")


def observation_to_event(observation: dict, twin_id: str) -> dict:
    """
    Map a single FHIR R4 Observation resource (including compound observations
    with component[]) to a ClinicalEvent dict.

    Parameters
    ----------
    observation : dict
        A parsed FHIR R4 Observation resource.
    twin_id : str
        The digital-twin identifier to embed in the event.

    Returns
    -------
    dict
        A ClinicalEvent conforming to contracts/clinical-event.schema.json v0.1.0.

    Raises
    ------
    ValueError
        For unsupported resource types, statuses, codes, units, or impossible values.
    """
    if not twin_id or not isinstance(twin_id, str):
        raise ValueError("twin_id must be a non-empty string")

    if observation.get("resourceType") != "Observation":
        raise ValueError(
            f"Expected resourceType 'Observation', got '{observation.get('resourceType')}'"
        )

    status = observation.get("status")
    if status not in _ACCEPTED_STATUSES:
        raise ValueError(
            f"Invalid Observation status '{status}'. Accepted: {sorted(_ACCEPTED_STATUSES)}."
        )

    payload: dict[str, Any] = {}
    missing_fields: list[str] = []
    categories_found: set[str] = set()

    # 1. Process top-level code if supported
    top_codes = _extract_codes(observation)
    matched_top = [c for c in top_codes if c in _ALL_SUPPORTED]
    if matched_top:
        primary_code = matched_top[0]
        field, val, missing, cat = _extract_field_value(primary_code, observation)
        payload[field] = val
        categories_found.add(cat)

    # 2. Process component[] array for compound observations
    components = observation.get("component", [])
    for comp in components:
        comp_codes = _extract_codes(comp)
        matched_comp = [c for c in comp_codes if c in _ALL_SUPPORTED]
        for c in matched_comp:
            field, val, missing, cat = _extract_field_value(c, comp)
            payload[field] = val
            categories_found.add(cat)

    if not payload:
        all_codes = top_codes + [c for comp in components for c in _extract_codes(comp)]
        raise ValueError(
            f"Unsupported observation code. Got {all_codes}. "
            f"Supported: {sorted(_ALL_SUPPORTED)}."
        )

    missing_fields = [k for k, v in payload.items() if v is None]

    # Determine event_type based on categories found
    if "PATHOLOGY" in categories_found:
        event_type = "PATHOLOGY_RESULT"
    elif "BIOMARKER" in categories_found:
        event_type = "BIOMARKER_RESULT"
    else:
        event_type = "DIAGNOSIS"

    effective_time = _extract_effective_time(observation)
    obs_id = observation.get("id") or str(uuid.uuid4())
    meta = observation.get("meta", {})
    received_time = meta.get("lastUpdated") or datetime.now(timezone.utc).isoformat()
    data_version = meta.get("versionId", "1")

    quality_status = "warning" if missing_fields else "valid"

    return {
        "schema_version": "0.1.0",
        "twin_id": twin_id,
        "event_id": f"evt_{obs_id}",
        "event_type": event_type,
        "effective_time": effective_time,
        "received_time": received_time,
        "source": "fhir_adapter",
        "quality_status": quality_status,
        "provenance": {
            "source_system": "fhir",
            "source_record_id": obs_id,
            "data_version": data_version,
        },
        "payload": payload,
    }


def bundle_to_events(bundle: dict, twin_id: str) -> tuple[list[dict], list[dict]]:
    """
    Extract all supported Observation entries from a FHIR R4 Bundle and map each
    to a ClinicalEvent. Unsupported or invalid observations are skipped with a
    warning message collected in the returned skip_log.

    Parameters
    ----------
    bundle : dict
        A parsed FHIR R4 Bundle (type: "collection" or "searchset").
    twin_id : str
        The digital-twin identifier.

    Returns
    -------
    tuple[list[dict], list[dict]]
        (events, skip_log) where each skip_log entry is {"resource_id": ..., "reason": ...}.
    """
    if bundle.get("resourceType") != "Bundle":
        raise ValueError(
            f"Expected resourceType 'Bundle', got '{bundle.get('resourceType')}'"
        )

    events: list[dict] = []
    skip_log: list[dict] = []

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") != "Observation":
            continue
        try:
            event = observation_to_event(resource, twin_id)
            events.append(event)
        except ValueError as exc:
            skip_log.append(
                {"resource_id": resource.get("id", "unknown"), "reason": str(exc)}
            )

    return events, skip_log


# ---------------------------------------------------------------------------
# Additional FHIR R4 Resource Adapters (Patient, Encounter, DiagnosticReport)
# ---------------------------------------------------------------------------


def patient_to_profile(patient: dict, twin_id: str | None = None) -> dict[str, Any]:
    """
    Extract demographic and administrative data from a FHIR R4 Patient resource
    into a canonical PatientProfile dictionary.
    """
    if patient.get("resourceType") != "Patient":
        raise ValueError(
            f"Expected resourceType 'Patient', got '{patient.get('resourceType')}'"
        )

    patient_id = str(patient.get("id") or uuid.uuid4())
    resolved_twin_id = twin_id or f"TWIN_{patient_id}"

    mrn = None
    for ident in patient.get("identifier", []):
        type_codings = ident.get("type", {}).get("coding", [])
        for c in type_codings:
            if c.get("code") == "MR":
                mrn = ident.get("value")
                break
        if not mrn and ident.get("value"):
            mrn = ident.get("value")

    raw_gender = patient.get("gender", "unknown")
    gender = raw_gender.lower() if isinstance(raw_gender, str) else "unknown"
    if gender not in ("female", "male", "other", "unknown"):
        gender = "unknown"

    birth_date = patient.get("birthDate")

    return {
        "patient_id": patient_id,
        "twin_id": resolved_twin_id,
        "mrn": mrn,
        "gender": gender,
        "birth_date": birth_date,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "source_system": "fhir",
            "active": patient.get("active", True),
        },
    }


def encounter_to_event(encounter: dict, twin_id: str) -> dict[str, Any]:
    """
    Translate a FHIR R4 Encounter resource (inpatient, ambulatory, surveillance,
    treatment) into a canonical ClinicalEvent dictionary.
    """
    if encounter.get("resourceType") != "Encounter":
        raise ValueError(
            f"Expected resourceType 'Encounter', got '{encounter.get('resourceType')}'"
        )
    if not twin_id or not isinstance(twin_id, str):
        raise ValueError("twin_id must be a non-empty string")

    enc_id = str(encounter.get("id") or uuid.uuid4())
    status = encounter.get("status", "finished")
    period = encounter.get("period", {})
    effective_time = (
        period.get("start")
        or period.get("end")
        or datetime.now(timezone.utc).isoformat()
    )
    meta = encounter.get("meta", {})
    received_time = meta.get("lastUpdated") or datetime.now(timezone.utc).isoformat()
    data_version = meta.get("versionId", "1")

    # Class: e.g. AMB, IMP, EMER
    enc_class_val = encounter.get("class", {})
    if isinstance(enc_class_val, dict):
        enc_class = enc_class_val.get("code", "AMB")
    else:
        enc_class = str(enc_class_val)

    reasons: list[str] = []
    for r in encounter.get("reasonCode", []):
        text = r.get("text") or (
            r.get("coding", [{}])[0].get("display") if r.get("coding") else None
        )
        if text:
            reasons.append(str(text))
    reason_str = "; ".join(reasons) if reasons else "surveillance"

    text_check = (reason_str + " " + str(encounter.get("type", []))).lower()
    if any(
        k in text_check
        for k in ("chemo", "radiation", "surgery", "mastectomy", "lumpectomy", "therapy")
    ):
        event_type = "TREATMENT"
    else:
        event_type = "FOLLOW_UP"

    payload: dict[str, Any] = {
        "encounter_id": enc_id,
        "encounter_class": enc_class,
        "status": status,
        "reason": reason_str,
    }

    return {
        "schema_version": "0.1.0",
        "twin_id": twin_id,
        "event_id": f"evt_enc_{enc_id}",
        "event_type": event_type,
        "effective_time": effective_time,
        "received_time": received_time,
        "source": "fhir_adapter",
        "quality_status": "valid",
        "provenance": {
            "source_system": "fhir",
            "source_record_id": enc_id,
            "data_version": data_version,
        },
        "payload": payload,
    }


def diagnostic_report_to_events(report: dict, twin_id: str) -> list[dict[str, Any]]:
    """
    Translate a FHIR R4 DiagnosticReport resource into canonical ClinicalEvent dicts,
    extracting contained observations, conclusions, and morphology codes.
    """
    if report.get("resourceType") != "DiagnosticReport":
        raise ValueError(
            f"Expected resourceType 'DiagnosticReport', got '{report.get('resourceType')}'"
        )
    if not twin_id or not isinstance(twin_id, str):
        raise ValueError("twin_id must be a non-empty string")

    events: list[dict[str, Any]] = []
    rep_id = str(report.get("id") or uuid.uuid4())
    effective_time = report.get("effectiveDateTime")
    if not effective_time:
        period = report.get("effectivePeriod", {})
        effective_time = (
            period.get("start")
            or period.get("end")
            or datetime.now(timezone.utc).isoformat()
        )
    meta = report.get("meta", {})
    received_time = meta.get("lastUpdated") or datetime.now(timezone.utc).isoformat()
    data_version = meta.get("versionId", "1")

    # 1. Unpack contained Observations if present
    for contained in report.get("contained", []):
        if contained.get("resourceType") == "Observation":
            try:
                if not contained.get("effectiveDateTime") and not contained.get(
                    "effectivePeriod"
                ):
                    contained["effectiveDateTime"] = effective_time
                evt = observation_to_event(contained, twin_id)
                events.append(evt)
            except ValueError:
                pass

    # 2. Extract conclusion or morphology
    conclusion = report.get("conclusion")
    conclusion_code = report.get("conclusionCode", [])
    morphology = None
    if conclusion_code:
        coding = conclusion_code[0].get("coding", [{}])
        morphology = coding[0].get("code")

    if morphology or conclusion:
        payload: dict[str, Any] = {}
        if morphology:
            payload["morphology_code"] = str(morphology)
        if conclusion:
            payload["conclusion"] = str(conclusion)

        events.append({
            "schema_version": "0.1.0",
            "twin_id": twin_id,
            "event_id": f"evt_dr_{rep_id}",
            "event_type": "DIAGNOSIS",
            "effective_time": effective_time,
            "received_time": received_time,
            "source": "fhir_adapter",
            "quality_status": "valid",
            "provenance": {
                "source_system": "fhir",
                "source_record_id": rep_id,
                "data_version": data_version,
            },
            "payload": payload,
        })

    return events


def synthea_bundle_to_canonical(
    bundle: dict, default_twin_id: str | None = None
) -> dict[str, Any]:
    """
    Ingest a complete Synthea or clinical FHIR R4 Bundle containing Patient,
    Encounter, DiagnosticReport, and Observation entries.

    Returns
    -------
    dict with keys:
      - patient_profile: PatientProfile dict or None
      - events: list of canonical ClinicalEvent dicts
      - skip_log: list of skipped resources with reason
    """
    if bundle.get("resourceType") != "Bundle":
        raise ValueError(
            f"Expected resourceType 'Bundle', got '{bundle.get('resourceType')}'"
        )

    patient_profile: dict[str, Any] | None = None
    events: list[dict[str, Any]] = []
    skip_log: list[dict[str, Any]] = []

    twin_id = default_twin_id

    # First pass: find Patient resource to establish twin identity
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        if res.get("resourceType") == "Patient":
            try:
                patient_profile = patient_to_profile(res, twin_id=twin_id)
                if not twin_id:
                    twin_id = patient_profile["twin_id"]
            except ValueError as exc:
                skip_log.append({"resource_id": res.get("id", "patient"), "reason": str(exc)})
            break

    if not twin_id:
        twin_id = f"TWIN_SYNTHEA_{uuid.uuid4().hex[:8]}"

    # Second pass: process Encounters, DiagnosticReports, and Observations
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        rtype = res.get("resourceType")

        if rtype == "Observation":
            try:
                evt = observation_to_event(res, twin_id)
                events.append(evt)
            except ValueError as exc:
                skip_log.append({"resource_id": res.get("id", "obs"), "reason": str(exc)})

        elif rtype == "Encounter":
            try:
                evt = encounter_to_event(res, twin_id)
                events.append(evt)
            except ValueError as exc:
                skip_log.append({"resource_id": res.get("id", "enc"), "reason": str(exc)})

        elif rtype == "DiagnosticReport":
            try:
                dr_events = diagnostic_report_to_events(res, twin_id)
                events.extend(dr_events)
            except ValueError as exc:
                skip_log.append({"resource_id": res.get("id", "dr"), "reason": str(exc)})

    return {
        "patient_profile": patient_profile,
        "events": events,
        "skip_log": skip_log,
        "twin_id": twin_id,
    }

