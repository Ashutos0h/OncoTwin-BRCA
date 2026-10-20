"""
Tests for data.src.etl — cohort ingestion, validation, cohort-to-events,
and anti-leakage splitting.
"""
import json
import pytest
from pathlib import Path

from data.src.etl import (
    run_etl,
    compute_missingness,
    cohort_to_events,
    patient_level_train_test_split,
    CohortValidationError,
    FEATURE_KEYS,
)
from data.src.validation import validate_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"
COHORT_FILE = SAMPLES_DIR / "synthetic-cohort.json"


def _write_cohort(tmp_path: Path, records: list) -> Path:
    p = tmp_path / "cohort.json"
    p.write_text(json.dumps(records))
    return p


# ---------------------------------------------------------------------------
# run_etl — happy path
# ---------------------------------------------------------------------------

class TestRunEtl:

    def test_loads_synthetic_cohort_file(self):
        records, warnings = run_etl(str(COHORT_FILE))
        assert len(records) == 3
        assert isinstance(warnings, list)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            run_etl("does_not_exist.json")

    def test_non_array_rejected(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text('{"not": "an array"}')
        with pytest.raises(ValueError, match="JSON array"):
            run_etl(str(p))

    def test_valid_minimal_record(self, tmp_path):
        records = [{"tumour_size_mm": 20.0, "grade": 2, "positive_nodes": 0}]
        p = _write_cohort(tmp_path, records)
        result, warnings = run_etl(str(p))
        assert len(result) == 1
        assert warnings == []

    def test_null_values_allowed(self, tmp_path):
        records = [{"tumour_size_mm": None, "grade": None, "her2_status": None}]
        p = _write_cohort(tmp_path, records)
        result, _ = run_etl(str(p))
        assert result[0]["tumour_size_mm"] is None

    def test_unknown_keys_produce_warning(self, tmp_path):
        records = [{"tumour_size_mm": 10.0, "mystery_field": "x"}]
        p = _write_cohort(tmp_path, records)
        _, warnings = run_etl(str(p))
        assert any("mystery_field" in w for w in warnings)

    def test_empty_array_allowed(self, tmp_path):
        p = _write_cohort(tmp_path, [])
        records, warnings = run_etl(str(p))
        assert records == []
        assert warnings == []


# ---------------------------------------------------------------------------
# run_etl — validation rules
# ---------------------------------------------------------------------------

class TestRunEtlValidation:

    def test_negative_tumour_size_rejected(self, tmp_path):
        p = _write_cohort(tmp_path, [{"tumour_size_mm": -1.0}])
        with pytest.raises(CohortValidationError, match="tumour_size_mm"):
            run_etl(str(p))

    def test_negative_nodes_rejected(self, tmp_path):
        p = _write_cohort(tmp_path, [{"positive_nodes": -3}])
        with pytest.raises(CohortValidationError, match="positive_nodes"):
            run_etl(str(p))

    def test_ki67_above_100_rejected(self, tmp_path):
        p = _write_cohort(tmp_path, [{"ki67_percent": 105.0}])
        with pytest.raises(CohortValidationError, match="ki67_percent"):
            run_etl(str(p))

    def test_ki67_negative_rejected(self, tmp_path):
        p = _write_cohort(tmp_path, [{"ki67_percent": -1.0}])
        with pytest.raises(CohortValidationError, match="ki67_percent"):
            run_etl(str(p))

    def test_grade_0_rejected(self, tmp_path):
        p = _write_cohort(tmp_path, [{"grade": 0}])
        with pytest.raises(CohortValidationError, match="grade"):
            run_etl(str(p))

    def test_grade_4_accepted(self, tmp_path):
        p = _write_cohort(tmp_path, [{"grade": 4}])
        records, _ = run_etl(str(p))
        assert records[0]["grade"] == 4

    def test_grade_5_rejected(self, tmp_path):
        p = _write_cohort(tmp_path, [{"grade": 5}])
        with pytest.raises(CohortValidationError, match="grade"):
            run_etl(str(p))

    def test_grade_float_rejected(self, tmp_path):
        p = _write_cohort(tmp_path, [{"grade": 2.5}])
        with pytest.raises(CohortValidationError, match="grade.*integer"):
            run_etl(str(p))

    def test_invalid_her2_string_rejected(self, tmp_path):
        p = _write_cohort(tmp_path, [{"her2_status": "indeterminate_invalid"}])
        with pytest.raises(CohortValidationError, match="her2_status"):
            run_etl(str(p))

    def test_her2_ordinal_score_accepted(self, tmp_path):
        p = _write_cohort(tmp_path, [{"her2_status": "3+"}, {"her2_status": "0"}])
        records, _ = run_etl(str(p))
        assert records[0]["her2_status"] == "3+"
        assert records[1]["her2_status"] == "0"

    def test_invalid_er_string_rejected(self, tmp_path):
        p = _write_cohort(tmp_path, [{"er_status": "unknown"}])
        with pytest.raises(CohortValidationError, match="er_status"):
            run_etl(str(p))

    def test_her2_valid_equivocal(self, tmp_path):
        p = _write_cohort(tmp_path, [{"her2_status": "equivocal"}])
        records, _ = run_etl(str(p))
        assert records[0]["her2_status"] == "equivocal"

    def test_non_dict_record_rejected(self, tmp_path):
        p = _write_cohort(tmp_path, ["not a dict"])
        with pytest.raises(CohortValidationError):
            run_etl(str(p))

    def test_tumour_size_string_rejected(self, tmp_path):
        p = _write_cohort(tmp_path, [{"tumour_size_mm": "big"}])
        with pytest.raises(CohortValidationError, match="tumour_size_mm.*numeric"):
            run_etl(str(p))


# ---------------------------------------------------------------------------
# compute_missingness
# ---------------------------------------------------------------------------

class TestComputeMissingness:

    def test_empty_records_all_missing(self):
        result = compute_missingness([])
        assert all(v == 1.0 for v in result.values())
        assert set(result.keys()) == FEATURE_KEYS

    def test_fully_populated_record_zero_missing(self):
        record = {
            "tumour_size_mm": 20.0,
            "grade": 2,
            "positive_nodes": 1,
            "her2_status": "positive",
            "er_status": "negative",
            "pr_status": "negative",
            "ki67_percent": 15.0,
            "morphology_code": "8500/3",
        }
        result = compute_missingness([record])
        assert all(v == 0.0 for v in result.values())

    def test_partial_missingness_rate(self):
        records = [
            {"tumour_size_mm": 20.0, "grade": None},
            {"tumour_size_mm": 30.0, "grade": 2},
        ]
        result = compute_missingness(records)
        assert result["grade"] == 0.5
        assert result["tumour_size_mm"] == 0.0

    def test_synthetic_cohort_file_missingness(self):
        records, _ = run_etl(str(COHORT_FILE))
        rates = compute_missingness(records)
        assert rates["her2_status"] == pytest.approx(1 / 3)
        assert rates["ki67_percent"] == pytest.approx(1 / 3)
        assert rates["morphology_code"] == pytest.approx(1 / 3)
        assert rates["tumour_size_mm"] == 0.0
        assert rates["grade"] == 0.0


# ---------------------------------------------------------------------------
# cohort_to_events (Backend Integration)
# ---------------------------------------------------------------------------

class TestCohortToEvents:

    def test_generates_schema_valid_events(self):
        records, _ = run_etl(str(COHORT_FILE))
        events = cohort_to_events(records)
        assert len(events) > 0
        for ev in events:
            validate_event(ev)  # Strict JSON Schema validation

    def test_categorises_events_properly(self):
        record = [{
            "twin_id": "TWIN_X",
            "record_id": "rec_01",
            "tumour_size_mm": 22.0,
            "grade": 2,
            "positive_nodes": 1,
            "her2_status": "positive",
            "er_status": "negative",
            "pr_status": "negative",
            "ki67_percent": 20.0,
            "morphology_code": "8500/3",
        }]
        events = cohort_to_events(record)
        event_types = {e["event_type"] for e in events}
        assert event_types == {"PATHOLOGY_RESULT", "BIOMARKER_RESULT", "DIAGNOSIS"}

    def test_sets_warning_when_fields_are_null(self):
        record = [{
            "twin_id": "TWIN_Y",
            "tumour_size_mm": 20.0,
            "grade": None,  # Missing field
        }]
        events = cohort_to_events(record)
        assert len(events) == 1
        assert events[0]["quality_status"] == "warning"


# ---------------------------------------------------------------------------
# patient_level_train_test_split (Anti-Leakage)
# ---------------------------------------------------------------------------

class TestPatientLevelSplit:

    def test_zero_patient_leakage(self):
        records = [
            {"twin_id": "P1", "tumour_size_mm": 10.0, "time": 1},
            {"twin_id": "P1", "tumour_size_mm": 12.0, "time": 2},
            {"twin_id": "P2", "tumour_size_mm": 20.0, "time": 1},
            {"twin_id": "P3", "tumour_size_mm": 30.0, "time": 1},
            {"twin_id": "P4", "tumour_size_mm": 40.0, "time": 1},
            {"twin_id": "P5", "tumour_size_mm": 50.0, "time": 1},
        ]
        train, test = patient_level_train_test_split(records, test_ratio=0.4, seed=123)
        assert len(train) > 0
        assert len(test) > 0

        train_patients = {r["twin_id"] for r in train}
        test_patients = {r["twin_id"] for r in test}

        # Strict anti-leakage guarantee
        assert train_patients.isdisjoint(test_patients)
        assert train_patients | test_patients == {"P1", "P2", "P3", "P4", "P5"}

        # Check P1 records stayed together in the same split
        if "P1" in train_patients:
            assert sum(1 for r in train if r["twin_id"] == "P1") == 2
        else:
            assert sum(1 for r in test if r["twin_id"] == "P1") == 2

    def test_preserves_intra_patient_temporal_order(self):
        records = [
            {"twin_id": "P1", "val": 1},
            {"twin_id": "P1", "val": 2},
            {"twin_id": "P1", "val": 3},
            {"twin_id": "P2", "val": 10},
        ]
        train, test = patient_level_train_test_split(records, test_ratio=0.5, seed=42)
        p1_records = [r["val"] for r in (train if any(r["twin_id"] == "P1" for r in train) else test)]
        assert p1_records == [1, 2, 3]

    def test_invalid_ratio_rejected(self):
        records = [{"twin_id": "P1"}, {"twin_id": "P2"}]
        with pytest.raises(ValueError, match="test_ratio"):
            patient_level_train_test_split(records, test_ratio=0.0)
        with pytest.raises(ValueError, match="test_ratio"):
            patient_level_train_test_split(records, test_ratio=1.0)

    def test_too_few_patients_rejected(self):
        records = [{"twin_id": "P1"}, {"twin_id": "P1"}]
        with pytest.raises(ValueError, match="at least 2 unique patients"):
            patient_level_train_test_split(records, test_ratio=0.5)

    def test_missing_patient_id_key_rejected(self):
        records = [{"wrong_key": "P1"}, {"wrong_key": "P2"}]
        with pytest.raises(ValueError, match="lacks required patient ID"):
            patient_level_train_test_split(records, test_ratio=0.5)
