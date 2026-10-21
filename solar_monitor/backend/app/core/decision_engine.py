"""Rule-based decision engine - ported from notebook Section 18.

Rules are unchanged:
  Healthy_Clean                 -> NO_ACTION
  Soiling_Dusty  (not persistent / below threshold) -> WAIT
  Soiling_Dusty  (>= threshold AND persistent)      -> START_CLEANING
  Partial_Shading               -> TILT_PANEL
  hotspot == YES (any class)    -> HOTSPOT_ALERT[_WITH_<condition>]   (class preserved)

Documented additions (do not alter the rules above):
  * `auto_actions` lists the actuator commands the engine may execute on its own: the base
    action's command (START_CLEANING / TILT_PANEL) is NOT withheld because a hotspot is present
    - the hotspot alert is a separate, additional safety output. There is no automatic hotspot
    "repair": that remains an explicit (simulated) operator action.
  * Combined soiling + partial shading: the ML model only emits ONE class, so when the class is
    Partial_Shading and the power shortfall is clearly larger than the shading seen on the thermal
    grid can explain, `secondary_condition` = "SOILING" is raised and START_CLEANING is queued as
    a secondary action (tilt first, then clean). The ML class itself is never rewritten.
  * `base_action` / `base_status` are returned so the UI can show the underlying
    condition's action next to the hotspot alert.
  * If the ML class is unavailable AND a hotspot is present, the hotspot alert is
    still raised (a model failure must not silence a thermal alarm).
  * NaN deviations are handled without crashing the reason text.
"""
from __future__ import annotations

import math

from ..config import SimConfig

VALID_ML_CLASSES = {"Healthy_Clean", "Soiling_Dusty", "Partial_Shading"}


def _fmt(dev) -> str:
    return "n/a" if dev is None or (isinstance(dev, float) and math.isnan(dev)) else f"{dev:.1f}"


class DecisionEngine:
    VALID_ML_CLASSES = VALID_ML_CLASSES

    def __init__(self, config: SimConfig):
        self.config = config

    def decide(self, ml_class, hotspot, deviation_pct, persistent, shading_loss_est_pct=None) -> dict:
        cfg = self.config
        dev_is_nan = deviation_pct is None or (isinstance(deviation_pct, float) and math.isnan(deviation_pct))
        hotspot_active = str(hotspot).upper() == "YES"
        dev_out = None if dev_is_nan else deviation_pct

        if ml_class not in VALID_ML_CLASSES:
            if hotspot_active:
                return {
                    "ml_class": ml_class, "hotspot": hotspot, "deviation_pct": dev_out,
                    "persistent_degrad": persistent,
                    "final_status": "HOTSPOT_DETECTED",
                    "recommended_action": "HOTSPOT_ALERT",
                    "base_status": "MODEL_UNAVAILABLE", "base_action": "MODEL_UNAVAILABLE",
                    "auto_actions": [], "secondary_condition": None,
                    "reason": f"Hotspot ALERT - ML class '{ml_class}' unavailable; underlying condition unknown.",
                }
            return {
                "ml_class": ml_class, "hotspot": hotspot, "deviation_pct": dev_out,
                "persistent_degrad": persistent,
                "final_status": "MODEL_UNAVAILABLE",
                "recommended_action": "MODEL_UNAVAILABLE",
                "base_status": "MODEL_UNAVAILABLE", "base_action": "MODEL_UNAVAILABLE",
                "auto_actions": [], "secondary_condition": None,
                "reason": f"ML class '{ml_class}' is unrecognised. No action taken.",
            }

        if ml_class == "Healthy_Clean":
            base_action, base_status = "NO_ACTION", "HEALTHY"
            base_reason = "Panel is clean and healthy; no intervention required."
        elif ml_class == "Soiling_Dusty":
            dev_ok = dev_is_nan or abs(deviation_pct) < cfg.soiling_dev_thresh_pct
            if dev_ok or not persistent:
                base_action, base_status = "WAIT", "SOILING_DETECTED"
                base_reason = (f"Soiling detected. Deviation={_fmt(deviation_pct)}% "
                               f"(threshold={cfg.soiling_dev_thresh_pct}%). "
                               "Condition not yet persistent enough to trigger cleaning.")
            else:
                base_action, base_status = "START_CLEANING", "CLEANING_REQUIRED"
                base_reason = (f"Soiling confirmed. Deviation={_fmt(deviation_pct)}% "
                               f"persisted for >={cfg.persist_cycles} cycles.")
        else:  # Partial_Shading
            base_action, base_status = "TILT_PANEL", "PARTIAL_SHADING"
            base_reason = ("Partial shading detected. Tilting/orientation correction requested. "
                           "Cleaning is NOT recommended for shading.")

        # Combined soiling + shading (single-class ML): residual shortfall the shading cannot explain.
        secondary = None
        if (ml_class == "Partial_Shading" and shading_loss_est_pct is not None and not dev_is_nan
                and deviation_pct - shading_loss_est_pct > cfg.soiling_dev_thresh_pct):
            secondary = "SOILING"
            base_status = "PARTIAL_SHADING_AND_SOILING"
            base_reason += (f" Power shortfall {_fmt(deviation_pct)}% exceeds the ~{shading_loss_est_pct:.1f}% explained by the "
                            "shaded area: concurrent soiling suspected - cleaning follows the tilt once the shortfall persists.")
        auto_actions = [a for a in (base_action, "START_CLEANING" if secondary and persistent else None)
                        if a in ("START_CLEANING", "TILT_PANEL")]

        if hotspot_active:
            if ml_class == "Soiling_Dusty":
                action, status = "HOTSPOT_ALERT_WITH_SOILING", "HOTSPOT_AND_SOILING"
            elif ml_class == "Partial_Shading":
                action, status = "HOTSPOT_ALERT_WITH_PARTIAL_SHADING", "HOTSPOT_AND_PARTIAL_SHADING"
            else:
                action, status = "HOTSPOT_ALERT", "HOTSPOT_DETECTED"
            reason = f"Hotspot ALERT (safety alert only - no automatic hotspot repair). {base_reason}"
        else:
            action, status, reason = base_action, base_status, base_reason

        return {
            "ml_class": ml_class, "hotspot": hotspot, "deviation_pct": dev_out,
            "persistent_degrad": persistent,
            "final_status": status, "recommended_action": action,
            "base_status": base_status, "base_action": base_action,
            "auto_actions": auto_actions, "secondary_condition": secondary,
            "reason": reason,
        }
