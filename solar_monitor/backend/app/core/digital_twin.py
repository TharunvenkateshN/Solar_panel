"""Expected-power model and Digital Twin - ported from notebook Section 16-17.

P_expected = P_STC * (G / G_STC) * (1 + gamma * (T - T_STC))
Health score and energy loss are PROVISIONAL simulation metrics.
"""
from __future__ import annotations

import math
from collections import deque

from ..config import SimConfig
from ..topics import utc_now


def pv_expected_power(irradiance_wm2: float, temperature_c: float, cfg: SimConfig) -> float:
    if irradiance_wm2 is None or irradiance_wm2 <= 0 or math.isnan(irradiance_wm2):
        return 0.0
    p = cfg.p_stc_w * (irradiance_wm2 / cfg.g_stc) * (1 + cfg.gamma * (temperature_c - cfg.t_stc))
    return max(0.0, round(p, 4))


HEALTH_WEIGHTS = {"performance": 1.0, "performance_cap": 60.0,
                  "hotspot_base": 20.0, "hotspot_per_deg": 1.0, "hotspot_cap": 40.0,
                  "shading_per_cool_fraction": 30.0, "shading_cap": 15.0, "soiling_flag": 5.0}
HEALTH_HEALTHY_MIN, HEALTH_DEGRADED_MIN = 80.0, 50.0


def composite_health(deviation_pct, ml_class, hotspot_active: bool, max_temp_c: float,
                     cool_pixels: int, cfg: SimConfig) -> dict:
    """Panel Health Score, 0-100 (SIMULATED ESTIMATE - not a validated real-world measurement).

        score = 100 - performance - hotspot - shading - soiling          (clamped to 0..100)
        performance = min(60, |power deviation %|)           shortfall vs the digital twin's expectation
        hotspot     = 0 if no hotspot else min(40, 20 + (max pixel temp - hotspot abs threshold))
        shading     = min(15, 30 * cool_pixels / 64)         only when the class is Partial_Shading
        soiling     = 5                                      only when the class is Soiling_Dusty
    The power term already carries most of the soiling/shading loss; the shading/soiling terms are
    small condition flags so a diagnosed fault is visible even before the shortfall is large.
    Bands: >= 80 Healthy, 50-79 Degraded, < 50 Critical; an active hotspot is never reported as Healthy.
    """
    w = HEALTH_WEIGHTS
    dev = None if deviation_pct is None or (isinstance(deviation_pct, float) and math.isnan(deviation_pct)) else deviation_pct
    perf = 0.0 if dev is None else min(w["performance_cap"], abs(dev) * w["performance"])
    hot = 0.0
    if hotspot_active:
        hot = min(w["hotspot_cap"], w["hotspot_base"] + max(0.0, max_temp_c - cfg.hotspot_abs_thresh_c) * w["hotspot_per_deg"])
    shade = min(w["shading_cap"], w["shading_per_cool_fraction"] * cool_pixels / 64) if ml_class == "Partial_Shading" else 0.0
    soil = w["soiling_flag"] if ml_class == "Soiling_Dusty" else 0.0
    score = round(max(0.0, min(100.0, 100.0 - perf - hot - shade - soil)), 1)
    if score < HEALTH_DEGRADED_MIN:
        status = "Critical"
    elif score < HEALTH_HEALTHY_MIN or hotspot_active:
        status = "Degraded"
    else:
        status = "Healthy"
    return {"score": score, "status": status, "simulated_estimate": True,
            "penalties": {"power_deviation": round(perf, 1), "hotspot": round(hot, 1),
                          "partial_shading": round(shade, 1), "soiling": round(soil, 1)},
            "formula": "100 - power deviation (max 60) - hotspot (20 + °C over threshold, max 40) "
                       "- shading (30 x cool-area fraction, max 15) - soiling flag (5)"}


class SolarDigitalTwin:
    def __init__(self, config: SimConfig):
        self.config = config
        self._history: deque = deque(maxlen=500)
        self._persist_count = 0
        self._cleaning_state = False
        self._tilt_angle = 90.0  # degrees (90 = vertical, notebook default)

    # -- notebook API ----------------------------------------------------------
    def expected_power(self, irradiance_wm2: float, temperature_c: float) -> float:
        return pv_expected_power(irradiance_wm2, temperature_c, self.config)

    @staticmethod
    def power_deviation(p_actual: float, p_expected: float) -> float:
        """Deviation (%) = (P_expected - P_actual) / P_expected * 100 (positive = shortfall)."""
        if p_expected <= 0:
            return float("nan")
        return round(((p_expected - p_actual) / p_expected) * 100, 2)

    @staticmethod
    def health_score(deviation_pct: float) -> float:
        """100% at zero deviation, decreasing linearly. PROVISIONAL."""
        if deviation_pct is None or math.isnan(deviation_pct):
            return float("nan")
        return round(max(0.0, 100.0 - abs(deviation_pct)), 2)

    def update(self, V, I, lux, temperature_C, ml_class, hotspot,
               irradiance_Wm2=None, use_lux_for_irr=False) -> dict:
        cfg = self.config
        p_actual = V * I

        if irradiance_Wm2 is None or (isinstance(irradiance_Wm2, float) and math.isnan(irradiance_Wm2)):
            if use_lux_for_irr:
                irradiance_Wm2 = lux * cfg.lux_to_irradiance
                irr_source = "lux_derived_UNCALIBRATED"
            else:
                irradiance_Wm2 = float("nan")
                irr_source = "unavailable"
        else:
            irr_source = "measured"

        p_exp = self.expected_power(irradiance_Wm2, temperature_C)
        dev = self.power_deviation(p_actual, p_exp)
        hs = self.health_score(dev)

        # Persistence: consecutive cycles with |deviation| above threshold.
        if not math.isnan(dev) and abs(dev) > cfg.soiling_dev_thresh_pct:
            self._persist_count += 1
        else:
            self._persist_count = 0
        persistent = self._persist_count >= cfg.persist_cycles

        # Energy loss per cycle (notebook assumes 1-minute sampling -> /60).
        energy_loss = round(max(0.0, p_exp - p_actual) / 60 * cfg.sim_minutes_per_tick, 4)

        state = {
            "voltage_V": round(V, 4),
            "current_A": round(I, 4),
            "power_actual_W": round(p_actual, 4),
            "lux": round(lux, 2),
            "temperature_C": round(temperature_C, 2),
            "irradiance_Wm2": None if math.isnan(irradiance_Wm2) else round(irradiance_Wm2, 2),
            "irradiance_source": irr_source,
            "power_expected_W": p_exp,
            "deviation_pct": None if math.isnan(dev) else dev,
            "health_score_pct": None if math.isnan(hs) else hs,
            "energy_loss_Wh_est": energy_loss,
            "ml_class": ml_class,
            "hotspot": hotspot,
            "persistent_degrad": persistent,
            "persist_count": self._persist_count,
            "persist_required": cfg.persist_cycles,
            "cleaning_state": self._cleaning_state,
            "tilt_angle_deg": self._tilt_angle,
            "timestamp": utc_now(),
        }
        self._history.append(state)
        return state

    # -- additions for the website --------------------------------------------
    def reset_persistence(self) -> None:
        self._persist_count = 0

    def set_actuator_state(self, tilt_angle_deg: float, cleaning_active: bool) -> None:
        self._tilt_angle = float(tilt_angle_deg)
        self._cleaning_state = bool(cleaning_active)
