"""Classifier adapter contract. Implement `ConditionClassifier` to plug in any model.

The pipeline only ever calls `predict(feature_bundle)` and reads a `Prediction`.
Rules every adapter must follow:
  * label is one of the three ML classes, or None if no valid prediction exists
  * confidence is only set when the underlying model really provides a probability
  * never raise out of predict(): return Prediction(label=None, error=...)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass

CLASSES = ("Healthy_Clean", "Soiling_Dusty", "Partial_Shading")  # hotspot is NOT an ML class


@dataclass
class Prediction:
    label: str | None
    confidence: float | None
    mode: str                       # "simulated" | "trained_model" | "unavailable"
    model_name: str | None = None
    note: str = ""
    error: str | None = None
    probabilities: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ConditionClassifier(ABC):
    mode: str = "unavailable"
    name: str = "unnamed"

    @abstractmethod
    def predict(self, features: dict) -> Prediction:
        """`features` is the bundle from ml.features.build_feature_bundle."""

    def info(self) -> dict:
        return {"mode": self.mode, "name": self.name}
