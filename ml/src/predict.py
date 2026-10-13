import argparse
import json
from pathlib import Path
try:
    import numpy as np
except ImportError:
    np = None

try:
    import joblib
except ImportError:
    joblib = None

try:
    import shap
except ImportError:
    shap = None

from scripts.validate_contracts import load_example, validate

MODEL_PATH = Path(__file__).parent.parent / 'models' / 'model.pkl'

def predict_demo(snapshot, *, prediction_id, audit_id, created_at):
    validate('feature-snapshot', snapshot)
    
    # Try to load real model, fallback to mock if missing
    model = None
    if joblib is not None and MODEL_PATH.exists():
        try:
            model = joblib.load(MODEL_PATH)
        except Exception:
            model = None
    
    features_dict = snapshot.get("features", {})
    # Default values if missing
    tumour_size = features_dict.get("tumour_size_mm", 20.0)
    if tumour_size is None: tumour_size = 20.0
    grade = features_dict.get("grade", 2)
    if grade is None: grade = 2
    positive_nodes = features_dict.get("positive_nodes", 0)
    if positive_nodes is None: positive_nodes = 0

    result = load_example('prediction')
    for key in ('twin_id', 'snapshot_id', 'state_version', 'data_version'):
        result[key] = snapshot[key]
    result.update(prediction_id=prediction_id, audit_id=audit_id, created_at=created_at)

    if model is not None and np is not None:
        try:
            x_input = np.array([[tumour_size, grade, positive_nodes]])
            # Generate real prediction
            probs = model.predict_proba(x_input)[0]
            risk = probs[1]
            
            result['is_mock'] = False
            result['model_name'] = type(model).__name__
            
            # Use metadata or getattr
            metadata_path = MODEL_PATH.with_suffix('.json')
            model_version = "unknown"
            if metadata_path.exists():
                try:
                    import json as _json
                    with open(metadata_path, 'r') as f_meta:
                        meta = _json.load(f_meta)
                        model_version = meta.get("version", "unknown")
                except Exception:
                    pass
            if model_version == "unknown":
                model_version = getattr(model, '__version__', getattr(model, 'version', 'unknown'))
            result['model_version'] = model_version
            
            result['risk_probability'] = float(risk)
            
            # Simple OOD and Confidence heuristic
            is_ood = tumour_size > 100 or positive_nodes > 30
            result['ood_flag'] = is_ood
            
            if is_ood:
                result['confidence'] = 'low'
            elif 0.3 < risk < 0.7:
                result['confidence'] = 'moderate'
            else:
                result['confidence'] = 'high'
                
            warnings = []
            if is_ood:
                warnings.append("Features out of typical distribution.")
            
            # SHAP values
            result['shap_values'] = []
            if shap is not None:
                try:
                    if type(model).__name__ in ["Pipeline", "LogisticRegression"]:
                        classifier = model.named_steps['classifier'] if hasattr(model, 'named_steps') else model
                        X_transformed = model.named_steps['imputer'].transform(x_input) if hasattr(model, 'named_steps') else x_input
                        explainer = shap.LinearExplainer(classifier, np.zeros((1, X_transformed.shape[1])))
                        s_vals = explainer.shap_values(X_transformed)
                        shap_vals = s_vals[1][0] if isinstance(s_vals, list) else s_vals[0]
                    else:
                        explainer = shap.TreeExplainer(model)
                        s_vals = explainer.shap_values(x_input)
                        shap_vals = s_vals[1][0] if isinstance(s_vals, list) else s_vals[0]
                    
                    result['shap_values'] = [
                        {"feature": "tumour_size_mm", "value": float(shap_vals[0])},
                        {"feature": "grade", "value": float(shap_vals[1])},
                        {"feature": "positive_nodes", "value": float(shap_vals[2])},
                    ]
                except Exception:
                    warnings.append("SHAP values could not be generated.")
                    
            result['warnings'] = warnings
            
        except Exception:
            # If prediction fails completely, ensure safe mock fallback
            result['is_mock'] = True
            result['shap_values'] = []
            result['ood_flag'] = None
            result['confidence'] = 'not_assessed'

    
    validate('prediction', result)
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    result = predict_demo(json.loads(args.snapshot.read_text()), prediction_id='pred_demo_001',
                          audit_id='audit_demo_001', created_at='2026-09-01T10:00:00Z')
    print(json.dumps(result, indent=2))
