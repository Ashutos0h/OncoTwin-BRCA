import re
import sys

def patch_fhir():
    with open('data/src/fhir_adapter.py', 'r', encoding='utf-8') as f:
        code = f.read()
    
    target = """        vq = observation.get("valueQuantity", {})
        unit = vq.get("unit")
        value = vq.get("value")
        if unit == "cm" and value is not None:
            value = value * 10.0
        elif unit != "mm":
            raise ValueError("Unsupported unit. Only 'mm' and 'cm' are supported for tumor size.")
        if value is None or value < 0:
            raise ValueError("Impossible or missing value for tumor size")
        payload["tumour_size_mm"] = value"""
    
    replacement = """        vq = observation.get("valueQuantity", {})
        value = vq.get("value")
        if value is None:
            payload["tumour_size_mm"] = None
        else:
            unit = vq.get("unit")
            if unit == "cm":
                value = value * 10.0
            elif unit != "mm":
                raise ValueError("Unsupported unit. Only 'mm' and 'cm' are supported for tumor size.")
            if value < 0:
                raise ValueError("Impossible negative value for tumor size")
            payload["tumour_size_mm"] = value"""
            
    code = code.replace(target, replacement)
    
    with open('data/src/fhir_adapter.py', 'w', encoding='utf-8') as f:
        f.write(code)

def patch_predict():
    with open('ml/src/predict.py', 'r', encoding='utf-8') as f:
        code = f.read()

    # The user asked:
    # 1. emit [] for shap_values and null for ood_flag when there is no model or it fails.
    # 2. remove result['model_version'] = "0.2.0-trained" hardcoding (or handle it for no model case)
    # 3. shap_vals = ... in except block must be removed, and instead shap_values = [] if SHAP fails.
    
    target = """    if model is not None:
        # Generate real prediction
        probs = model.predict_proba(x_input)[0]
        risk = probs[1]
        
        result['is_mock'] = False
        result['model_name'] = type(model).__name__
        result['model_version'] = "0.2.0-trained"
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
            except Exception:
                shap_vals = np.array([risk * 0.5, risk * 0.3, risk * 0.2])
        else:
            shap_vals = np.array([risk * 0.5, risk * 0.3, risk * 0.2])
            
        result['shap_values'] = [
            {"feature": "tumour_size_mm", "value": float(shap_vals[0])},
            {"feature": "grade", "value": float(shap_vals[1])},
            {"feature": "positive_nodes", "value": float(shap_vals[2])},
        ]
    
    validate('prediction', result)"""
    
    replacement = """    if model is not None:
        try:
            # Generate real prediction
            probs = model.predict_proba(x_input)[0]
            risk = probs[1]
            
            result['is_mock'] = False
            result['model_name'] = type(model).__name__
            # Use real version or default
            result['model_version'] = getattr(model, 'version', '0.2.0')
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
                    pass
        except Exception:
            # model predicting failed
            result['shap_values'] = []
            result['ood_flag'] = None
    else:
        # no model
        result['shap_values'] = []
        result['ood_flag'] = None
    
    validate('prediction', result)"""
    
    code = code.replace(target, replacement)
    
    with open('ml/src/predict.py', 'w', encoding='utf-8') as f:
        f.write(code)

if __name__ == '__main__':
    patch_fhir()
    patch_predict()
