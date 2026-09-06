# AI/ML Lead

Read root AGENTS.md, README.md, contracts/README.md, all five schemas and
docs/architecture.md. Own `ml/`; coordinate changes elsewhere.

## First task

Extend the tested FeatureSnapshot to Prediction boundary. Agree feature dictionary with Data and Backend, outcome/horizon/censoring and patient-level splits before training. Then compare Logistic Regression and XGBoost, calibrate and evaluate. Mock output must remain explicit; do not invent SHAP, OOD or confidence results.

## Acceptance

Run `python -m pytest ml/tests` and `python scripts/validate_contracts.py` from root.
Deliver a focused PR with behavior, validation results and remaining limitations.
Do not change shared fields to fit module code. Raise contract proposals explicitly.

## Copy into your Codex session

I am the AI/ML Lead. Read AGENTS.md and docs/leads/ml.md and the shared
contracts, then implement the first task inside ml/. Preserve shared schemas.
Add meaningful tests and report the checks you ran.
