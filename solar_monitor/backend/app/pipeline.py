"""One reading through the full chain:

 virtual sensors -> feature preparation -> ML classification -> hotspot detection
   -> expected-performance comparison -> decision engine

(Corrective action and post-action verification are stateful over time and live in engine.py.)
The pipeline consumes ONLY the telemetry message, so it behaves identically whether the message
arrived in-process or through an MQTT broker.
"""
from __future__ import annotations

import numpy as np

from .config import SimConfig
from .core.decision_engine import DecisionEngine
from .core.digital_twin import SolarDigitalTwin
from .core.hotspot import HotspotDetector
from .ml.base import ConditionClassifier
from .ml.features import build_feature_bundle

ML_UNAVAILABLE = "MODEL_UNAVAILABLE"


class Pipeline:
    def __init__(self, config: SimConfig, classifier: ConditionClassifier):
        self.config = config
        self.classifier = classifier
        self.twin = SolarDigitalTwin(config)
        self.detector = HotspotDetector(config)
        self.engine = DecisionEngine(config)

    def set_classifier(self, classifier: ConditionClassifier) -> None:
        self.classifier = classifier

    def reset(self) -> None:
        self.twin = SolarDigitalTwin(self.config)

    @staticmethod
    def parse(telemetry: dict) -> dict:
        try:
            ina, bh, amg = telemetry["ina219"], telemetry["bh1750"], telemetry["amg8833"]
            grid = np.array(amg["grid"], dtype=float)
            if grid.shape != (8, 8):
                raise ValueError(f"thermal grid must be 8x8, got {grid.shape}")
            return {
                "V": float(ina["voltage_V"]), "I": float(ina["current_A"]),
                "lux": float(bh["lux"]), "grid": grid,
                "actuators": telemetry.get("actuators", {}),
            }
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"Malformed telemetry: {type(e).__name__}: {e}") from e

    def process(self, telemetry: dict) -> dict:
        cfg = self.config
        s = self.parse(telemetry)
        V, I, lux, grid = s["V"], s["I"], s["lux"], s["grid"]
        act = s["actuators"]
        self.twin.set_actuator_state(act.get("tilt_angle_deg", 90.0), act.get("cleaning_active", False))

        # 1-2. sensors + feature preparation
        panel_temp = float(grid.mean())
        irradiance = lux * cfg.lux_to_irradiance  # UNCALIBRATED lux -> W/m2
        expected = self.twin.expected_power(irradiance, panel_temp)
        features = build_feature_bundle(V, I, irradiance, panel_temp, expected, grid, cfg)

        # 3. ML classification (simulated stand-in or trained model, behind one interface)
        pred = self.classifier.predict(features)
        ml_class = pred.label if pred.label else ML_UNAVAILABLE

        # 4. hotspot detection (independent of ML)
        hs = self.detector.detect(grid)

        # 5. expected-performance comparison
        twin = self.twin.update(V, I, lux, panel_temp, ml_class, hs["hotspot_detected"],
                                irradiance_Wm2=None, use_lux_for_irr=True)

        # 6. decision engine
        dec = self.engine.decide(ml_class, hs["hotspot_detected"], twin["deviation_pct"], twin["persistent_degrad"])

        thermal = {**hs, "grid": grid.round(2).tolist()}
        result = {
            "electrical": {"voltage_V": twin["voltage_V"], "current_A": twin["current_A"], "power_W": twin["power_actual_W"]},
            "lux": twin["lux"], "irradiance_Wm2": twin["irradiance_Wm2"], "irradiance_source": twin["irradiance_source"],
            "panel_temp_C": round(panel_temp, 2),
            "features": features, "ml": pred.to_dict(), "thermal": thermal, "twin": twin, "decision": dec,
            "actuators": act,
        }
        result["stages"] = self._stages(result)
        return result

    def _stages(self, r: dict) -> list[dict]:
        e, t, ml, tw, d, f = r["electrical"], r["thermal"], r["ml"], r["twin"], r["decision"], r["features"]
        cfg = self.config
        ml_state = "done" if ml["label"] else "error"
        ml_head = ml["label"] or "MODEL_UNAVAILABLE"
        hs_yes = t["hotspot_detected"] == "YES"
        trig = [n for n, on in (("max > %.0f C" % cfg.hotspot_abs_thresh_c, t["cond_abs_triggered"]),
                                ("max-mean > %.0f C and >= %d hot px" % (cfg.hotspot_delta_thresh_c, cfg.hot_pixel_thresh), t["cond_delta_triggered"])) if on]
        return [
            {"id": "sensors", "title": "Virtual sensors", "state": "done",
             "headline": f"{e['power_W']:.2f} W  |  {r['lux']:.0f} lx",
             "details": {"INA219": f"{e['voltage_V']:.2f} V x {e['current_A']:.3f} A", "BH1750": f"{r['lux']:.0f} lx",
                         "AMG8833": f"8x8 grid, max {t['max_temp_C']:.1f} C"}},
            {"id": "features", "title": "Feature preparation", "state": "done",
             "headline": f"{len(f['iv_features'])} I-V features",
             "details": {"I-V curve": "synthesised from operating point", "Pmpp": f"{f['iv_features']['Pmpp']:.2f} W",
                         "Voc / Isc": f"{f['iv_features']['Voc']:.1f} V / {f['iv_features']['Isc']:.2f} A",
                         "Power ratio": f"{f['derived']['power_ratio']}", "Cool pixels": f"{f['derived']['cool_pixel_count']}"}},
            {"id": "ml", "title": "ML classification", "state": ml_state, "headline": ml_head,
             "details": {"Mode": {"simulated": "SIMULATED stand-in", "trained_model": "Trained model", "unavailable": "Unavailable"}[ml["mode"]],
                         "Confidence": f"{ml['confidence']:.2f}" if ml["confidence"] is not None else "n/a (no trained model)"}},
            {"id": "hotspot", "title": "Hotspot detection", "state": "alert" if hs_yes else "done",
             "headline": "HOTSPOT: " + t["hotspot_detected"],
             "details": {"Max / mean": f"{t['max_temp_C']:.1f} / {t['mean_temp_C']:.1f} C", "Hot pixels": str(t["hot_pixel_count"]),
                         "Rule fired": ", ".join(trig) if trig else "none"}},
            {"id": "twin", "title": "Expected vs measured", "state": "warn" if (tw["deviation_pct"] or 0) > cfg.soiling_dev_thresh_pct else "done",
             "headline": f"dev {tw['deviation_pct']:.1f} %" if tw["deviation_pct"] is not None else "dev n/a",
             "details": {"Expected": f"{tw['power_expected_W']:.2f} W", "Measured": f"{tw['power_actual_W']:.2f} W",
                         "Health": f"{tw['health_score_pct']:.1f} %" if tw["health_score_pct"] is not None else "n/a",
                         "Persistence": f"{min(tw['persist_count'], tw['persist_required'])}/{tw['persist_required']}"}},
            {"id": "decision", "title": "Decision engine",
             "state": "alert" if hs_yes else ("warn" if d["recommended_action"] in ("START_CLEANING", "TILT_PANEL") else "done"),
             "headline": d["recommended_action"],
             "details": {"Status": d["final_status"], "Underlying": d["base_action"], "Reason": d["reason"]}},
        ]
