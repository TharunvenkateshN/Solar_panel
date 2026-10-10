"""Choose the classifier at startup / on reload.

SOLAR_CLASSIFIER env var:
  auto       (default) trained model if its files exist, else the simulated stand-in.
             If the files exist but fail to load, the failure is SHOWN (no silent fallback).
  simulated  always the simulated stand-in.
  model      trained model required; if it cannot load, predictions are 'unavailable'.
"""
from __future__ import annotations

import os
from pathlib import Path

from ..config import SimConfig
from .base import ConditionClassifier, Prediction
from .joblib_model import MODEL_FILE, JoblibClassifier, ModelLoadError
from .simulated import SimulatedClassifier


class UnavailableClassifier(ConditionClassifier):
    mode = "unavailable"
    name = "No classifier"

    def __init__(self, error: str):
        self.error = error

    def predict(self, features: dict) -> Prediction:
        return Prediction(label=None, confidence=None, mode=self.mode, error=self.error,
                          note="Model unavailable - no class is produced.")

    def info(self) -> dict:
        return {"mode": self.mode, "name": self.name, "error": self.error}


def load_classifier(models_dir: Path, config: SimConfig, preference: str | None = None):
    pref = (preference or os.environ.get("SOLAR_CLASSIFIER", "auto")).lower()
    models_dir = Path(models_dir)
    sim = SimulatedClassifier(config)

    def finish(clf: ConditionClassifier, **extra):
        info = {**clf.info(), "preference": pref, "models_dir": str(models_dir),
                "expected_file": MODEL_FILE, "fallback_reason": None, "error": None, **extra}
        return clf, info

    if pref == "simulated":
        return finish(sim, fallback_reason="SOLAR_CLASSIFIER=simulated")
    try:
        return finish(JoblibClassifier.load(models_dir))
    except FileNotFoundError:
        if pref == "model":
            err = f"{MODEL_FILE} not found in {models_dir} (SOLAR_CLASSIFIER=model)."
            return finish(UnavailableClassifier(err), error=err)
        return finish(sim, fallback_reason=f"{MODEL_FILE} not found in {models_dir}")
    except ModelLoadError as e:
        return finish(UnavailableClassifier(str(e)), error=str(e))
