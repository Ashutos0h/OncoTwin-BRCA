import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.models import AuditRecord, ClinicalEvent, FeatureSnapshot, Prediction, TwinState


ROOT = Path(__file__).resolve().parents[2]
MODELS = {
    "clinical-event": ClinicalEvent,
    "twin-state": TwinState,
    "feature-snapshot": FeatureSnapshot,
    "prediction": Prediction,
    "audit-record": AuditRecord,
}


@pytest.mark.parametrize("name,model", MODELS.items())
def test_models_accept_contract_examples(name, model):
    value = json.loads((ROOT / "contracts" / "examples" / f"{name}.json").read_text())
    assert model.model_validate(value).model_dump(mode="json") == value


@pytest.mark.parametrize("name,model", MODELS.items())
def test_models_reject_extra_fields(name, model):
    value = json.loads((ROOT / "contracts" / "examples" / f"{name}.json").read_text())
    value["unexpected"] = "not allowed"
    with pytest.raises(ValidationError):
        model.model_validate(value)


def test_prediction_rejects_json_schema_type_coercion():
    value = json.loads((ROOT / "contracts/examples/prediction.json").read_text())
    value["risk_probability"] = "0.31"
    value["state_version"] = "1"
    value["is_mock"] = 1
    with pytest.raises(ValidationError):
        Prediction.model_validate(value)


def test_unique_contract_array_is_enforced():
    value = json.loads((ROOT / "contracts/examples/twin-state.json").read_text())
    value["event_ids"] = [value["event_ids"][0], value["event_ids"][0]]
    with pytest.raises(ValidationError):
        TwinState.model_validate(value)
