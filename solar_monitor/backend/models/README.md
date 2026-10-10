# Trained-model drop-in folder

Copy the three files the notebook writes (Section 11) into this folder:

| File | Required | Content |
|---|---|---|
| `solar_panel_condition_model.joblib` | yes | `dict` with `pipe`, `label_encoder`, `feature_cols` |
| `model_metadata.json` | no (recommended) | model name, classes, LOO accuracy, caveats - shown in the UI |
| `feature_schema.json` | no (recommended) | `feature_cols` - must equal the list stored in the model |

Then either restart `python run.py` or press **Reload model from backend/models** at the bottom of the dashboard.

What happens:

* **Files absent** - the simulated stand-in classifier is used (clearly labelled in the UI, no confidence shown).
* **Files present and valid** - the trained model is used. The header chip changes to `Trained model: <name>`, ML confidence appears (`predict_proba`), and every prediction is shown as-is.
* **Files present but broken** (wrong classes, schema mismatch, scikit-learn/xgboost version problem, unpickling error) - the failure is shown in the UI and the class becomes `MODEL_UNAVAILABLE`. There is no silent fallback to the simulated classifier. Fix the file or set `SOLAR_CLASSIFIER=simulated`.

The model was trained with scikit-learn 1.6.1 on Python 3.13 (notebook output). Install the same scikit-learn version if loading fails: `pip install scikit-learn==1.6.1` (and `xgboost` if the saved model is XGBoost).

Inputs: the 19 features of `feature_schema.json`. Because no I-V sweep hardware exists, `backend/app/ml/features.py` synthesises an I-V curve from the simulated operating point and runs the notebook's own `extract_iv_features` on it. A model trained on 7 samples is only a demonstration; its output on synthetic curves is not evidence of real-world accuracy.

To plug in a different kind of model, implement `ConditionClassifier.predict(features) -> Prediction` (`backend/app/ml/base.py`) and return it from `backend/app/ml/loader.py`.
