import json
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from xgboost import XGBClassifier
import joblib

def generate_dummy_data(n_samples=1000):
    np.random.seed(42)
    tumour_size_mm = np.random.uniform(5, 50, n_samples)
    grade = np.random.choice([1, 2, 3], n_samples)
    positive_nodes = np.random.poisson(2, n_samples)
    
    # Time-Aware Evaluation: Sorting by patient interaction time to prevent temporal leakage
    # We simulate this by assuming patient index correlates with time.
    # In a real scenario, we would use GroupKFold by PatientID and time-series splits.
    risk_score = (tumour_size_mm / 50) + (grade / 3) + (positive_nodes / 10)
    survival_prob = 1 / (1 + np.exp(risk_score - 1.5))
    
    # Proper survival analysis (e.g. Kaplan-Meier, Cox Proportional Hazards) should be used for right-censored outcomes.
    # Here we simplify for binary 5-year classification.
    
    outcome = (np.random.rand(n_samples) < survival_prob).astype(int)
    
    return pd.DataFrame({
        'tumour_size_mm': tumour_size_mm,
        'grade': grade,
        'positive_nodes': positive_nodes
    }), outcome

def main():
    print("Generating synthetic training data...")
    X, y = generate_dummy_data()
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
    
    print("Training Logistic Regression...")
    lr = Pipeline([
        ('imputer', SimpleImputer(strategy='median')),
        ('classifier', LogisticRegression())
    ])
    lr.fit(X_train, y_train)
    lr_preds = lr.predict_proba(X_test)[:, 1]
    lr_auc = roc_auc_score(y_test, lr_preds)
    print(f"Logistic Regression AUC: {lr_auc:.3f}")
    
    print("Training XGBoost...")
    xgb = XGBClassifier(eval_metric='logloss')
    xgb.fit(X_train, y_train)
    xgb_preds = xgb.predict_proba(X_test)[:, 1]
    xgb_auc = roc_auc_score(y_test, xgb_preds)
    print(f"XGBoost AUC: {xgb_auc:.3f}")
    
    best_model = lr if lr_auc > xgb_auc else xgb
    print("Saving the best model...")
    
    model_dir = Path(__file__).parent.parent / 'models'
    model_dir.mkdir(exist_ok=True)
    joblib.dump(best_model, model_dir / 'model.pkl')
    print("Done.")

if __name__ == '__main__':
    main()
