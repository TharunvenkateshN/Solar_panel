"""Simulated stand-in classifier (used while the trained model is not connected).

It is NOT a trained model: a transparent rule set over observable signatures.
It derives the class from the generated data (cool thermal region, power shortfall)
rather than from the selected scenario's label, and it reports NO confidence.

  cool pixels >= N                      -> Partial_Shading  (localised cool region)
  power / expected < 1 - threshold      -> Soiling_Dusty    (uniform shortfall, no cool region)
  otherwise                             -> Healthy_Clean
"""
from __future__ import annotations

from ..config import SimConfig
from .base import ConditionClassifier, Prediction


class SimulatedClassifier(ConditionClassifier):
    mode = "simulated"
    name = "Simulated rule-based classifier"

    def __init__(self, config: SimConfig):
        self.config = config

    def predict(self, features: dict) -> Prediction:
        d = features["derived"]
        cfg = self.config
        cool, ratio = d["cool_pixel_count"], d["power_ratio"]
        if cool >= cfg.classifier_cool_pixels_min:
            label, why = "Partial_Shading", f"{cool} pixels >{cfg.classifier_cool_delta_c} C below median (localised cool region)"
        elif ratio is not None and ratio < 1 - cfg.soiling_dev_thresh_pct / 100:
            label, why = "Soiling_Dusty", f"power ratio {ratio:.2f} below {1 - cfg.soiling_dev_thresh_pct / 100:.2f} with no cool region"
        else:
            label, why = "Healthy_Clean", f"power ratio {ratio if ratio is not None else 'n/a'} and no cool region"
        return Prediction(label=label, confidence=None, mode=self.mode, model_name=self.name,
                          note=f"SIMULATED classifier (trained model not connected): {why}")
