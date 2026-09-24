import re

with open('ml/src/predict.py', 'r') as f:
    code = f.read()

target = '''    if model is not None:
        # Generate real prediction
        probs = model.predict_proba(x_input)[0]
        risk = probs[1]
        
        result['is_mock'] = False
        result['model_name'] = type(model).__name__
        result['model_version'] = getattr(model, '__version__', 'unknown')
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
        result['warnings'] = warnings
        
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
                pass'''

replacement = '''    if model is not None:
        try:
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
'''

if target in code:
    code = code.replace(target, replacement)
    with open('ml/src/predict.py', 'w') as f:
        f.write(code)
    print("Replaced successfully in predict.py")
else:
    print("Target not found in predict.py")

with open('data/src/fhir_adapter.py', 'r') as f:
    code = f.read()

target2 = '''    if "21889-1" in codes:
        # Tumor Size
        vq = observation.get("valueQuantity", {})
        unit = vq.get("unit")
        value = vq.get("value")
        if unit == "cm" and value is not None:
            value = value * 10.0
        elif unit != "mm" and value is not None:
            raise ValueError("Unsupported unit. Only 'mm' and 'cm' are supported for tumor size.")
        if value is not None and value < 0:
            raise ValueError("Impossible or missing value for tumor size")
        payload["tumour_size_mm"] = value
    elif "33732-9" in codes:
        # Histologic Grade
        vq = observation.get("valueQuantity", {})
        value = vq.get("value")
        if value is not None and value not in [1, 2, 3, 4]:
            payload["grade"] = None
        else:
            payload["grade"] = int(value) if value is not None else None
    elif "21893-3" in codes:
        # Positive Nodes
        vq = observation.get("valueQuantity", {})
        value = vq.get("value")
        if value is not None and value < 0:
            raise ValueError("Nodes cannot be negative")
        payload["positive_nodes"] = int(value) if value is not None else None'''

replacement2 = '''    if "21889-1" in codes:
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
            payload["positive_nodes"] = int(value)'''

if target2 in code:
    code = code.replace(target2, replacement2)
    with open('data/src/fhir_adapter.py', 'w') as f:
        f.write(code)
    print("Replaced successfully in fhir_adapter.py")
else:
    print("Target not found in fhir_adapter.py")
