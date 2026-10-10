"""Adapter for the notebook's saved model (Section 11).

Expected files in backend/models/:
  solar_panel_condition_model.joblib   dict {'pipe', 'label_encoder', 'feature_cols'}   (required)
  model_metadata.json                  classes, loo_accuracy, caveats ...               (optional)
  feature_schema.json                  feature_cols, descriptions                       (optional)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .base import CLASSES, ConditionClassifier, Prediction

MODEL_FILE = "solar_panel_condition_model.joblib"
METADATA_FILE = "model_metadata.json"
SCHEMA_FILE = "feature_schema.json"


class ModelLoadError(Exception):
    pass


class JoblibClassifier(ConditionClassifier):
    mode = "trained_model"

    def __init__(self, bundle: dict, metadata: dict, schema: dict, path: Path, warnings: list[str]):
        self.pipe = bundle["pipe"]
        self.label_encoder = bundle["label_encoder"]
        self.feature_cols = list(bundle["feature_cols"])
        self.metadata = metadata
        self.schema = schema
        self.path = path
        self.warnings = warnings
        self.name = metadata.get("model_name", "trained model")

    @classmethod
    def load(cls, models_dir: Path) -> "JoblibClassifier":
        path = Path(models_dir) / MODEL_FILE
        if not path.exists():
            raise FileNotFoundError(str(path))
        try:
            import joblib
            bundle = joblib.load(path)
        except Exception as e:  # unpickling errors, missing xgboost, sklearn version skew ...
            raise ModelLoadError(f"Could not load {MODEL_FILE}: {type(e).__name__}: {e}") from e
        for key in ("pipe", "label_encoder", "feature_cols"):
            if not isinstance(bundle, dict) or key not in bundle:
                raise ModelLoadError(f"{MODEL_FILE} must be a dict with keys pipe/label_encoder/feature_cols (missing '{key}').")

        warnings: list[str] = []
        classes = [str(c) for c in bundle["label_encoder"].classes_]
        bad = [c for c in classes if c not in CLASSES]
        if bad or len(classes) != len(CLASSES):
            raise ModelLoadError(f"Model classes {classes} do not match the expected 3 classes {list(CLASSES)}.")

        metadata, schema = {}, {}
        for fname, store in ((METADATA_FILE, "metadata"), (SCHEMA_FILE, "schema")):
            fpath = Path(models_dir) / fname
            if fpath.exists():
                try:
                    data = json.loads(fpath.read_text(encoding="utf-8"))
                except Exception as e:
                    raise ModelLoadError(f"{fname} is not valid JSON: {e}") from e
                (metadata if store == "metadata" else schema).update(data)
            else:
                warnings.append(f"{fname} not found (optional).")
        if schema and list(schema.get("feature_cols", [])) != list(bundle["feature_cols"]):
            raise ModelLoadError("feature_schema.json feature_cols differ from the feature_cols stored in the model.")
        return cls(bundle, metadata, schema, path, warnings)

    def predict(self, features: dict) -> Prediction:
        try:
            iv = features["iv_features"]
            missing = [c for c in self.feature_cols if c not in iv]
            if missing:
                raise ValueError(f"missing features: {missing}")
            row = [float(iv[c]) for c in self.feature_cols]
            if any(math.isinf(x) for x in row):
                raise ValueError("non-finite feature value")
            import numpy as np
            X = np.array([row])
            y = self.pipe.predict(X)[0]
            label = str(self.label_encoder.inverse_transform([y])[0])
            if label not in CLASSES:
                raise ValueError(f"model returned unknown class '{label}'")
            confidence, probs = None, None
            if hasattr(self.pipe, "predict_proba"):
                try:
                    p = self.pipe.predict_proba(X)[0]
                    names = [str(c) for c in self.label_encoder.classes_]
                    probs = {n: round(float(v), 4) for n, v in zip(names, p)}
                    confidence = round(float(max(p)), 4)
                except Exception:
                    pass
            return Prediction(label=label, confidence=confidence, mode=self.mode, model_name=self.name,
                              probabilities=probs,
                              note="Trained model prediction. Features were synthesised from the operating point (no I-V sweep).")
        except Exception as e:
            return Prediction(label=None, confidence=None, mode="unavailable", model_name=self.name,
                              error=f"Inference failed: {type(e).__name__}: {e}")

    def info(self) -> dict:
        m = self.metadata
        return {
            "mode": self.mode, "name": self.name, "path": str(self.path),
            "classes": m.get("classes"), "n_training_samples": m.get("n_training_samples"),
            "loo_accuracy": m.get("loo_accuracy"), "evaluation_method": m.get("evaluation_method"),
            "caveats": m.get("CAVEATS", []), "warnings": self.warnings,
        }
