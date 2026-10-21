"""
Cohort ingestion, validation, and anti-leakage splitting boundary for OncoTwin-BRCA.

Features:
- Validates synthetic cohort datasets against the agreed feature dictionary.
- Translates cohort records into schema-conforming ClinicalEvent dicts ready for
  Backend ingestion (`cohort_to_events`).
- Anti-leakage patient-level train/test split utility (`patient_level_train_test_split`).
- Per-feature missingness analysis (`compute_missingness`).

Data Dictionary (agreed with ML and Backend leads)
--------------------------------------------------
Field              Type     Constraints        Notes
tumour_size_mm     float    ≥ 0                Largest tumour dimension in mm
grade              int      1, 2, 3, or 4      Nottingham 1–3 + Grade 4 (undifferentiated)
positive_nodes     int      ≥ 0                Number of node-positive regional nodes
her2_status        str|null positive/negative/equivocal  IHC result (supports 0, 1+, 2+, 3+)
er_status          str|null positive/negative            IHC result
pr_status          str|null positive/negative            IHC result
ki67_percent       float|null 0–100            Proliferation index (%)
morphology_code    str|null   ICD-O-3          e.g. "8500/3"
"""
from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Recognised numeric fields (must be ≥ 0 when present)
_NON_NEG_NUMERIC = {"tumour_size_mm", "positive_nodes", "ki67_percent"}
# Valid grade values (1–3 Nottingham, 4 undifferentiated)
_VALID_GRADES = {1, 2, 3, 4}
# Valid IHC string values
_IHC_FIELDS = {"her2_status", "er_status", "pr_status"}
_IHC_VALUES = {"positive", "negative", "equivocal", "0", "0+", "1", "1+", "2", "2+", "3", "3+"}

# All recognised feature keys (from agreed feature dictionary)
FEATURE_KEYS = {
    "tumour_size_mm",
    "grade",
    "positive_nodes",
    "her2_status",
    "er_status",
    "pr_status",
    "ki67_percent",
    "morphology_code",
}

# Subsets for mapping cohort records to distinct ClinicalEvent types
_PATHOLOGY_FIELDS = {"tumour_size_mm", "grade", "positive_nodes"}
_BIOMARKER_FIELDS = {"her2_status", "er_status", "pr_status", "ki67_percent"}
_DIAGNOSIS_FIELDS = {"morphology_code"}


class CohortValidationError(ValueError):
    """Raised when a cohort record fails validation."""


def _validate_record(record: dict[str, Any], index: int) -> list[str]:
    """
    Validate a single cohort record against the feature dictionary.
    Returns a list of warning strings (empty = clean).
    Raises CohortValidationError for impossible values.
    """
    warnings: list[str] = []

    if not isinstance(record, dict):
        raise CohortValidationError(
            f"Record {index} is not an object (dict). Got {type(record).__name__}."
        )

    # Check for unrecognised keys (warn, don't reject — schema is extensible)
    unknown = (
        set(record.keys())
        - FEATURE_KEYS
        - {"twin_id", "record_id", "timestamp", "effective_time", "recurrence_5yr", "_missing_mask"}
    )
    if unknown:
        warnings.append(f"Record {index}: unknown keys {sorted(unknown)} (ignored)")

    # Non-negative numeric constraints
    for field in _NON_NEG_NUMERIC:
        val = record.get(field)
        if val is not None:
            if not isinstance(val, (int, float)):
                raise CohortValidationError(
                    f"Record {index}: '{field}' must be numeric, got {type(val).__name__}."
                )
            if val < 0:
                raise CohortValidationError(
                    f"Record {index}: '{field}' must be ≥ 0, got {val}."
                )
            if field == "ki67_percent" and val > 100:
                raise CohortValidationError(
                    f"Record {index}: 'ki67_percent' must be ≤ 100, got {val}."
                )

    # Grade constraints (1–4)
    grade = record.get("grade")
    if grade is not None:
        if not isinstance(grade, int):
            raise CohortValidationError(
                f"Record {index}: 'grade' must be an integer, got {type(grade).__name__}."
            )
        if grade not in _VALID_GRADES:
            raise CohortValidationError(
                f"Record {index}: 'grade' must be between 1 and 4. Got {grade}."
            )

    # IHC status constraints
    for field in _IHC_FIELDS:
        val = record.get(field)
        if val is not None:
            if not isinstance(val, str):
                raise CohortValidationError(
                    f"Record {index}: '{field}' must be a string or null, "
                    f"got {type(val).__name__}."
                )
            if val.lower() not in _IHC_VALUES:
                raise CohortValidationError(
                    f"Record {index}: '{field}' value '{val}' not in "
                    f"{sorted(_IHC_VALUES)}."
                )

    return warnings


def run_etl(source_file: str) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Load and validate a synthetic cohort JSON file.

    The file must contain a JSON array of feature records. Each record
    may include any subset of the agreed feature dictionary keys plus
    optional 'twin_id', 'record_id', and 'effective_time'.

    Parameters
    ----------
    source_file : str
        Path to a synthetic cohort JSON file (must exist).

    Returns
    -------
    records : list[dict]
        Validated cohort records (all impossible-value records rejected).
    warnings : list[str]
        Non-fatal warnings (e.g. unknown keys).

    Raises
    ------
    FileNotFoundError
        If the source file does not exist.
    ValueError
        If the file is not a JSON array.
    CohortValidationError
        If any record contains an impossible value.
    """
    path = Path(source_file)
    if not path.exists():
        raise FileNotFoundError(f"Cohort source '{source_file}' not found.")

    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    if not isinstance(raw, list):
        raise ValueError(
            f"Expected cohort file to contain a JSON array. Got {type(raw).__name__}."
        )

    all_warnings: list[str] = []
    validated: list[dict[str, Any]] = []

    for idx, record in enumerate(raw):
        w = _validate_record(record, idx)
        all_warnings.extend(w)
        validated.append(record)

    return validated, all_warnings


def compute_missingness(records: list[dict[str, Any]]) -> dict[str, float]:
    """
    Compute per-feature missingness rate across the cohort.

    Parameters
    ----------
    records : list[dict]
        Validated cohort records from run_etl().

    Returns
    -------
    dict[str, float]
        Mapping of feature key → fraction of records where the value is None
        or the key is absent entirely. Values in [0.0, 1.0].
    """
    if not records:
        return {k: 1.0 for k in FEATURE_KEYS}

    n = len(records)
    missing_counts: dict[str, int] = {k: 0 for k in FEATURE_KEYS}
    for record in records:
        for key in FEATURE_KEYS:
            if record.get(key) is None:
                missing_counts[key] += 1

    return {k: missing_counts[k] / n for k in FEATURE_KEYS}


def cohort_to_events(
    records: list[dict[str, Any]],
    default_effective_time: str | None = None,
    source_system: str = "cohort_etl",
) -> list[dict[str, Any]]:
    """
    Translate synthetic cohort records into schema-conforming ClinicalEvent dicts.

    Each cohort record is mapped into up to three granular events:
      - PATHOLOGY_RESULT (tumour_size_mm, grade, positive_nodes)
      - BIOMARKER_RESULT (her2_status, er_status, pr_status, ki67_percent)
      - DIAGNOSIS (morphology_code)

    All generated events conform to contracts/clinical-event.schema.json v0.1.0
    and are ready for direct ingestion via the Backend API.

    Parameters
    ----------
    records : list[dict]
        Validated cohort records.
    default_effective_time : str, optional
        RFC3339 datetime string to use if the record doesn't specify one.
    source_system : str
        Provenance label (default: "cohort_etl").

    Returns
    -------
    list[dict]
        List of ClinicalEvent dicts.
    """
    events: list[dict[str, Any]] = []
    now_utc = datetime.now(timezone.utc).isoformat()

    for idx, rec in enumerate(records):
        twin_id = rec.get("twin_id") or f"SYNTHETIC_TWIN_{idx+1:03d}"
        rec_id = rec.get("record_id") or f"rec_{idx+1:03d}"
        effective_time = (
            rec.get("effective_time")
            or rec.get("timestamp")
            or default_effective_time
            or now_utc
        )

        # 1. Pathology Result Event
        path_payload = {k: rec[k] for k in _PATHOLOGY_FIELDS if k in rec}
        if path_payload:
            has_missing = any(v is None for v in path_payload.values())
            events.append({
                "schema_version": "0.1.0",
                "twin_id": twin_id,
                "event_id": f"evt_path_{rec_id}_{uuid.uuid4().hex[:6]}",
                "event_type": "PATHOLOGY_RESULT",
                "effective_time": effective_time,
                "received_time": now_utc,
                "source": "cohort_adapter",
                "quality_status": "warning" if has_missing else "valid",
                "provenance": {
                    "source_system": source_system,
                    "source_record_id": f"{rec_id}_path",
                    "data_version": "synthetic-0.1.0",
                },
                "payload": path_payload,
            })

        # 2. Biomarker Result Event
        bio_payload = {k: rec[k] for k in _BIOMARKER_FIELDS if k in rec}
        if bio_payload:
            has_missing = any(v is None for v in bio_payload.values())
            events.append({
                "schema_version": "0.1.0",
                "twin_id": twin_id,
                "event_id": f"evt_bio_{rec_id}_{uuid.uuid4().hex[:6]}",
                "event_type": "BIOMARKER_RESULT",
                "effective_time": effective_time,
                "received_time": now_utc,
                "source": "cohort_adapter",
                "quality_status": "warning" if has_missing else "valid",
                "provenance": {
                    "source_system": source_system,
                    "source_record_id": f"{rec_id}_bio",
                    "data_version": "synthetic-0.1.0",
                },
                "payload": bio_payload,
            })

        # 3. Diagnosis Event
        diag_payload = {k: rec[k] for k in _DIAGNOSIS_FIELDS if k in rec}
        if diag_payload:
            has_missing = any(v is None for v in diag_payload.values())
            events.append({
                "schema_version": "0.1.0",
                "twin_id": twin_id,
                "event_id": f"evt_diag_{rec_id}_{uuid.uuid4().hex[:6]}",
                "event_type": "DIAGNOSIS",
                "effective_time": effective_time,
                "received_time": now_utc,
                "source": "cohort_adapter",
                "quality_status": "warning" if has_missing else "valid",
                "provenance": {
                    "source_system": source_system,
                    "source_record_id": f"{rec_id}_diag",
                    "data_version": "synthetic-0.1.0",
                },
                "payload": diag_payload,
            })

    return events


def patient_level_train_test_split(
    records: list[dict[str, Any]],
    patient_id_key: str = "twin_id",
    test_ratio: float = 0.2,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Split cohort records into train and test sets strictly at the patient level.

    Anti-Leakage Guarantees:
      - All records for any single patient are placed entirely in train OR test.
      - set(train_patient_ids) ∩ set(test_patient_ids) is strictly EMPTY.
      - Relative temporal order of records within each patient is preserved.

    Parameters
    ----------
    records : list[dict]
        List of cohort records, each having `patient_id_key`.
    patient_id_key : str
        Dictionary key identifying the patient/twin (default: "twin_id").
    test_ratio : float
        Fraction of unique patients to assign to the test set (0.0 < test_ratio < 1.0).
    seed : int
        Random seed for reproducible patient partitioning.

    Returns
    -------
    train_records : list[dict]
    test_records : list[dict]

    Raises
    ------
    ValueError
        If test_ratio is out of bounds or if any record lacks patient_id_key.
    """
    if not (0.0 < test_ratio < 1.0):
        raise ValueError(f"test_ratio must be strictly between 0 and 1, got {test_ratio}")

    if not records:
        return [], []

    # Group records by patient ID while preserving within-patient ordering
    patient_records: dict[str, list[dict[str, Any]]] = {}
    for idx, rec in enumerate(records):
        pid = rec.get(patient_id_key)
        if not pid:
            raise ValueError(
                f"Record at index {idx} lacks required patient ID key '{patient_id_key}'"
            )
        patient_records.setdefault(str(pid), []).append(rec)

    unique_patients = sorted(patient_records.keys())
    n_patients = len(unique_patients)

    if n_patients < 2:
        raise ValueError(
            f"Cannot split cohort: requires at least 2 unique patients, found {n_patients}"
        )

    # Deterministic seeded shuffle of patient IDs
    rng = random.Random(seed)
    shuffled_patients = list(unique_patients)
    rng.shuffle(shuffled_patients)

    n_test = max(1, int(round(n_patients * test_ratio)))
    # Ensure at least 1 train and 1 test patient
    if n_test >= n_patients:
        n_test = n_patients - 1

    test_patient_ids = set(shuffled_patients[:n_test])
    train_patient_ids = set(shuffled_patients[n_test:])

    # Strict anti-leakage invariant check
    assert not (train_patient_ids & test_patient_ids), "Patient leakage detected!"

    train_records: list[dict[str, Any]] = []
    test_records: list[dict[str, Any]] = []

    for pid in shuffled_patients:
        if pid in test_patient_ids:
            test_records.extend(patient_records[pid])
        else:
            train_records.extend(patient_records[pid])

    return train_records, test_records


# ---------------------------------------------------------------------------
# Extended ETL Pipeline: Normalization, Missingness Masks, and 3-Way Splitting
# ---------------------------------------------------------------------------


def _is_none_or_nan(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and (val != val):  # IEEE NaN check
        return True
    if isinstance(val, str) and val.strip().lower() in ("nan", "none", "null", ""):
        return True
    return False


def clean_and_normalize_record(
    record: dict[str, Any], index: int = 0
) -> tuple[dict[str, Any], list[str]]:
    """
    Cleans and normalizes a single cohort record:
      - Unit normalization (cm → mm if indicated, lowercases categorical IHC)
      - Nottingham grade integer normalization
      - Missingness mask generation
      - Timestamp standardization
    """
    cleaned: dict[str, Any] = {}
    notes: list[str] = []

    # Preserve identifiers
    cleaned["twin_id"] = str(record.get("twin_id") or f"TWIN_PATIENT_{index+1:04d}")
    if "record_id" in record:
        cleaned["record_id"] = str(record["record_id"])

    # Effective time normalization
    raw_time = record.get("effective_time") or record.get("timestamp")
    if raw_time and not _is_none_or_nan(raw_time):
        try:
            dt = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
            cleaned["effective_time"] = dt.isoformat()
        except Exception:
            cleaned["effective_time"] = datetime.now(timezone.utc).isoformat()
    else:
        cleaned["effective_time"] = datetime.now(timezone.utc).isoformat()

    # Tumour size (mm)
    raw_size = record.get("tumour_size_mm")
    if not _is_none_or_nan(raw_size):
        try:
            val_size = float(raw_size)
            if val_size < 0:
                raise CohortValidationError(f"Negative tumour size {val_size}")
            cleaned["tumour_size_mm"] = round(val_size, 2)
        except ValueError:
            raise CohortValidationError(f"Invalid tumour size {raw_size}")
    else:
        cleaned["tumour_size_mm"] = None

    # Histologic grade (1-4)
    raw_grade = record.get("grade")
    if not _is_none_or_nan(raw_grade):
        try:
            val_grade = int(float(raw_grade))
            if val_grade not in _VALID_GRADES:
                raise CohortValidationError(f"Invalid grade {val_grade}; must be 1-4")
            cleaned["grade"] = val_grade
        except (ValueError, TypeError):
            raise CohortValidationError(f"Grade must be integer 1-4, got {raw_grade}")
    else:
        cleaned["grade"] = None

    # Positive lymph nodes
    raw_nodes = record.get("positive_nodes")
    if not _is_none_or_nan(raw_nodes):
        try:
            val_nodes = int(float(raw_nodes))
            if val_nodes < 0:
                raise CohortValidationError(f"Negative lymph nodes {val_nodes}")
            cleaned["positive_nodes"] = val_nodes
        except (ValueError, TypeError):
            raise CohortValidationError(f"Invalid node count {raw_nodes}")
    else:
        cleaned["positive_nodes"] = None

    # IHC Receptors
    for field in ("her2_status", "er_status", "pr_status"):
        raw_val = record.get(field)
        if not _is_none_or_nan(raw_val):
            s_val = str(raw_val).strip().lower()
            if s_val in ("pos", "positive", "3", "3+"):
                cleaned[field] = "positive"
            elif s_val in ("neg", "negative", "0", "0+", "1", "1+"):
                cleaned[field] = "negative"
            elif s_val in ("equivocal", "indeterminate", "2", "2+"):
                cleaned[field] = "equivocal" if field == "her2_status" else "negative"
            else:
                raise CohortValidationError(f"Unsupported {field} value: {raw_val}")
        else:
            cleaned[field] = None

    # Ki-67 percent
    raw_ki67 = record.get("ki67_percent")
    if not _is_none_or_nan(raw_ki67):
        try:
            val_ki67 = float(raw_ki67)
            if not (0.0 <= val_ki67 <= 100.0):
                raise CohortValidationError(f"Ki-67 percentage must be 0-100, got {val_ki67}")
            cleaned["ki67_percent"] = round(val_ki67, 2)
        except (ValueError, TypeError):
            raise CohortValidationError(f"Invalid Ki-67 value {raw_ki67}")
    else:
        cleaned["ki67_percent"] = None

    # Morphology code
    raw_morph = record.get("morphology_code")
    cleaned["morphology_code"] = (
        str(raw_morph).strip() if not _is_none_or_nan(raw_morph) else None
    )

    # Preserve outcome label if present (e.g. recurrence_5yr)
    if "recurrence_5yr" in record:
        cleaned["recurrence_5yr"] = int(record["recurrence_5yr"])

    # Generate binary missingness mask (1 = missing, 0 = present)
    mask = {k: (1 if cleaned.get(k) is None else 0) for k in FEATURE_KEYS}
    cleaned["_missing_mask"] = mask

    return cleaned, notes


def run_full_etl_pipeline(
    raw_records: list[dict[str, Any]],
    source_name: str = "synthetic",
    data_version: str = "v1.0.0",
) -> dict[str, Any]:
    """
    Executes the complete canonical ETL pipeline:
      Raw Dataset
          ↓
      Schema Validation
          ↓
      Cleaning & Duplicate Removal
          ↓
      Normalization
          ↓
      Missingness Detection & Masking
          ↓
      Canonical Mapping (ClinicalEvents)
          ↓
      Feature Dataset

    Returns a comprehensive result dictionary with cleaned records,
    missingness rates, missingness masks, canonical events, and SHA-256 fingerprint.
    """
    import hashlib

    # 1. Deduplicate by unique patient or record ID
    seen_ids: set[str] = set()
    deduped_raw: list[dict[str, Any]] = []
    for r in raw_records:
        uid = str(r.get("twin_id") or r.get("record_id") or id(r))
        if uid not in seen_ids:
            seen_ids.add(uid)
            deduped_raw.append(r)

    # 2. Cleaning and Normalization
    cleaned_records: list[dict[str, Any]] = []
    all_warnings: list[str] = []
    for idx, r in enumerate(deduped_raw):
        cleaned_rec, notes = clean_and_normalize_record(r, idx)
        all_warnings.extend(notes)
        w = _validate_record(cleaned_rec, idx)
        all_warnings.extend(w)
        cleaned_records.append(cleaned_rec)

    # 3. Missingness Detection
    missingness_rates = compute_missingness(cleaned_records)

    # 4. Canonical Mapping (to ClinicalEvents)
    events = cohort_to_events(cleaned_records, source_system=f"{source_name}_etl")

    # 5. Compute SHA-256 fingerprint for data versioning
    serialized = json.dumps(cleaned_records, sort_keys=True, default=str).encode("utf-8")
    content_hash = hashlib.sha256(serialized).hexdigest()

    return {
        "source": source_name,
        "data_version": data_version,
        "content_sha256": content_hash,
        "total_records": len(cleaned_records),
        "cleaned_records": cleaned_records,
        "missingness_rates": missingness_rates,
        "canonical_events": events,
        "warnings": all_warnings,
    }


def patient_level_three_way_split(
    records: list[dict[str, Any]],
    patient_id_key: str = "twin_id",
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Strict 3-way partition (train, validation, test) enforced at the patient level.

    Anti-Leakage Guarantees:
      - set(train) ∩ set(val) == ∅
      - set(train) ∩ set(test) == ∅
      - set(val) ∩ set(test) == ∅
      - Total patients partitioned = 100% of unique patients.
    """
    total_ratio = train_ratio + val_ratio + test_ratio
    if abs(total_ratio - 1.0) > 1e-4:
        raise ValueError(f"Ratios must sum to 1.0 (got {total_ratio})")

    # Group by patient
    patient_records: dict[str, list[dict[str, Any]]] = {}
    for idx, rec in enumerate(records):
        pid = rec.get(patient_id_key)
        if not pid:
            raise ValueError(f"Record {idx} lacks patient key '{patient_id_key}'")
        patient_records.setdefault(str(pid), []).append(rec)

    unique_patients = sorted(patient_records.keys())
    n_patients = len(unique_patients)
    if n_patients < 3:
        raise ValueError(
            f"3-way split requires at least 3 unique patients, found {n_patients}"
        )

    rng = random.Random(seed)
    shuffled_patients = list(unique_patients)
    rng.shuffle(shuffled_patients)

    n_val = max(1, int(round(n_patients * val_ratio)))
    n_test = max(1, int(round(n_patients * test_ratio)))
    n_train = n_patients - n_val - n_test
    if n_train < 1:
        n_train = 1
        if n_val > 1:
            n_val -= 1
        elif n_test > 1:
            n_test -= 1

    val_pids = set(shuffled_patients[:n_val])
    test_pids = set(shuffled_patients[n_val : n_val + n_test])
    train_pids = set(shuffled_patients[n_val + n_test :])

    # Zero-leakage verification
    assert not (train_pids & val_pids), "Leakage between train and validation!"
    assert not (train_pids & test_pids), "Leakage between train and test!"
    assert not (val_pids & test_pids), "Leakage between validation and test!"

    train_recs: list[dict[str, Any]] = []
    val_recs: list[dict[str, Any]] = []
    test_recs: list[dict[str, Any]] = []

    for pid in shuffled_patients:
        recs = patient_records[pid]
        if pid in train_pids:
            train_recs.extend(recs)
        elif pid in val_pids:
            val_recs.extend(recs)
        else:
            test_recs.extend(recs)

    return train_recs, val_recs, test_recs


def generate_cohort_statistics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Computes summary cohort statistics including sample size, grade distribution,
    IHC positive rates, and missingness rates.
    """
    if not records:
        return {"n_records": 0}

    n = len(records)
    grades = [r.get("grade") for r in records if r.get("grade") is not None]
    her2_pos = sum(1 for r in records if r.get("her2_status") == "positive")
    er_pos = sum(1 for r in records if r.get("er_status") == "positive")
    pr_pos = sum(1 for r in records if r.get("pr_status") == "positive")

    sizes = [
        float(r["tumour_size_mm"])
        for r in records
        if r.get("tumour_size_mm") is not None
    ]
    mean_size = sum(sizes) / len(sizes) if sizes else 0.0

    return {
        "n_patients": len(set(r.get("twin_id", str(i)) for i, r in enumerate(records))),
        "n_records": n,
        "mean_tumour_size_mm": round(mean_size, 2),
        "grade_counts": {g: grades.count(g) for g in (1, 2, 3, 4)},
        "her2_positive_count": her2_pos,
        "er_positive_count": er_pos,
        "pr_positive_count": pr_pos,
        "missingness": compute_missingness(records),
    }

