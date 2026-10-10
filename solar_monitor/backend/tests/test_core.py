"""Notebook-ported components: sensors, thermal/hotspot, digital twin, decision engine."""
import math

import numpy as np
import pytest

from app.config import SimConfig
from app.core.decision_engine import DecisionEngine
from app.core.digital_twin import SolarDigitalTwin
from app.core.hotspot import HotspotDetector
from app.core.sensors import VirtualBH1750, VirtualINA219
from app.core.thermal import VirtualAMG8833


def test_ina219_power_is_v_times_i_and_range_checked():
    r = VirtualINA219().read(15.55, 1.55)
    assert r["power_W"] == pytest.approx(15.55 * 1.55, abs=1e-3)
    with pytest.raises(ValueError):
        VirtualINA219().read(31.0, 1.0)
    with pytest.raises(ValueError):
        VirtualINA219().read(10.0, 11.0)


def test_bh1750_parametric_reading_is_noisy_around_target():
    bh = VirtualBH1750(rng_seed=1)
    vals = [bh.read_target(100000, 0.01)["lux"] for _ in range(200)]
    assert abs(np.mean(vals) - 100000) < 500
    assert np.std(vals) > 100  # it really is noisy, not a constant


def test_expected_power_matches_formula():
    cfg = SimConfig()
    twin = SolarDigitalTwin(cfg)
    assert twin.expected_power(1000, 25) == pytest.approx(30.0)
    assert twin.expected_power(500, 25) == pytest.approx(15.0)
    assert twin.expected_power(1000, 50) == pytest.approx(30.0 * (1 - 0.004 * 25))
    assert twin.expected_power(0, 25) == 0.0


def test_deviation_and_health():
    assert SolarDigitalTwin.power_deviation(20, 25) == pytest.approx(20.0)
    assert SolarDigitalTwin.power_deviation(25, 25) == 0.0
    assert math.isnan(SolarDigitalTwin.power_deviation(5, 0))
    assert SolarDigitalTwin.health_score(20.0) == 80.0
    assert SolarDigitalTwin.health_score(150.0) == 0.0


def test_persistence_requires_three_consecutive_cycles_and_resets():
    twin = SolarDigitalTwin(SimConfig())
    bad = dict(V=14.0, I=1.2, lux=100000, temperature_C=40, ml_class="Soiling_Dusty", hotspot="NO")
    flags = [twin.update(**bad, use_lux_for_irr=True)["persistent_degrad"] for _ in range(3)]
    assert flags == [False, False, True]
    good = twin.update(V=14.0, I=1.55, lux=100000, temperature_C=40, ml_class="Healthy_Clean", hotspot="NO", use_lux_for_irr=True)
    assert good["persist_count"] == 0 and not good["persistent_degrad"]


def test_persist_cycles_is_configurable():
    cfg = SimConfig()
    cfg.update({"persist_cycles": 2})
    twin = SolarDigitalTwin(cfg)
    bad = dict(V=14.0, I=1.2, lux=100000, temperature_C=40, ml_class="Soiling_Dusty", hotspot="NO", use_lux_for_irr=True)
    assert [twin.update(**bad)["persistent_degrad"] for _ in range(2)] == [False, True]


def _grid(base=40.0):
    return np.full((8, 8), base)


def test_hotspot_rules():
    det = HotspotDetector(SimConfig())
    assert det.detect(_grid())["hotspot_detected"] == "NO"

    g = _grid(); g[3, 3] = 70                       # absolute rule (>65), single pixel
    r = det.detect(g)
    assert r["hotspot_detected"] == "YES" and r["cond_abs_triggered"] and (3, 3) == (r["hotspot_row"], r["hotspot_col"])

    g = _grid(); g[3, 3] = 60                       # delta rule needs >=2 hot pixels: single pixel -> NO
    assert det.detect(g)["hotspot_detected"] == "NO"

    g = _grid(); g[3:5, 3:5] = 60                   # 4 pixels +20 C, max 60 < 65 -> delta rule
    r = det.detect(g)
    assert r["hotspot_detected"] == "YES" and r["cond_delta_triggered"] and not r["cond_abs_triggered"]
    assert sorted(map(tuple, r["hot_pixels"])) == [(3, 3), (3, 4), (4, 3), (4, 4)]


def test_hotspot_thresholds_are_configurable():
    cfg = SimConfig()
    g = _grid(); g[3, 3] = 70
    assert HotspotDetector(cfg).detect(g)["hotspot_detected"] == "YES"
    cfg.update({"hotspot_abs_thresh_c": 80})
    assert HotspotDetector(cfg).detect(g)["hotspot_detected"] == "NO"


def test_notebook_thermal_scenarios_keep_their_hotspot_labels():
    det = HotspotDetector(SimConfig())
    for seed in range(20):
        amg = VirtualAMG8833(rng_seed=seed)
        assert det.detect(amg.read("hotspot")["grid"])["hotspot_detected"] == "YES", seed
        for sc in ("normal", "mild_variation", "soiling", "shading"):
            assert det.detect(amg.read(sc)["grid"])["hotspot_detected"] == "NO", (seed, sc)


@pytest.mark.parametrize("ml,hs,dev,pers,action,status", [
    ("Healthy_Clean", "NO", 5.0, False, "NO_ACTION", "HEALTHY"),
    ("Soiling_Dusty", "NO", 8.0, False, "WAIT", "SOILING_DETECTED"),
    ("Soiling_Dusty", "NO", 15.0, False, "WAIT", "SOILING_DETECTED"),
    ("Soiling_Dusty", "NO", 15.0, True, "START_CLEANING", "CLEANING_REQUIRED"),
    ("Soiling_Dusty", "NO", 8.0, True, "WAIT", "SOILING_DETECTED"),
    ("Partial_Shading", "NO", 35.0, True, "TILT_PANEL", "PARTIAL_SHADING"),
    ("Healthy_Clean", "YES", 3.0, False, "HOTSPOT_ALERT", "HOTSPOT_DETECTED"),
    ("Soiling_Dusty", "YES", 12.0, True, "HOTSPOT_ALERT_WITH_SOILING", "HOTSPOT_AND_SOILING"),
    ("Partial_Shading", "YES", 30.0, True, "HOTSPOT_ALERT_WITH_PARTIAL_SHADING", "HOTSPOT_AND_PARTIAL_SHADING"),
    ("UNKNOWN", "NO", 5.0, False, "MODEL_UNAVAILABLE", "MODEL_UNAVAILABLE"),
])
def test_decision_table(ml, hs, dev, pers, action, status):
    d = DecisionEngine(SimConfig()).decide(ml, hs, dev, pers)
    assert (d["recommended_action"], d["final_status"]) == (action, status)
    assert d["ml_class"] == ml and d["hotspot"] == hs  # both inputs preserved


def test_hotspot_overlay_preserves_underlying_action():
    d = DecisionEngine(SimConfig()).decide("Soiling_Dusty", "YES", 15.0, True)
    assert d["base_action"] == "START_CLEANING" and d["recommended_action"] == "HOTSPOT_ALERT_WITH_SOILING"
    d = DecisionEngine(SimConfig()).decide("Partial_Shading", "YES", 30.0, False)
    assert d["base_action"] == "TILT_PANEL"


def test_hotspot_alert_survives_model_failure():
    d = DecisionEngine(SimConfig()).decide("MODEL_UNAVAILABLE", "YES", 3.0, False)
    assert d["recommended_action"] == "HOTSPOT_ALERT"


def test_cleaning_threshold_is_configurable():
    cfg = SimConfig(); cfg.update({"soiling_dev_thresh_pct": 20})
    eng = DecisionEngine(cfg)
    assert eng.decide("Soiling_Dusty", "NO", 15.0, True)["recommended_action"] == "WAIT"
    assert eng.decide("Soiling_Dusty", "NO", 25.0, True)["recommended_action"] == "START_CLEANING"


def test_nan_deviation_does_not_crash():
    d = DecisionEngine(SimConfig()).decide("Soiling_Dusty", "NO", float("nan"), True)
    assert d["recommended_action"] == "WAIT" and d["deviation_pct"] is None


def test_config_validation():
    cfg = SimConfig()
    with pytest.raises(ValueError):
        cfg.update({"persist_cycles": 0})
    with pytest.raises(ValueError):
        cfg.update({"nonsense": 1})
    assert cfg.persist_cycles == 3  # unchanged after a rejected update
    assert cfg.update({"persist_cycles": 5}) == ["persist_cycles"]
