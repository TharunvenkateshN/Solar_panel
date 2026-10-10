"""UI controls must change the actual simulated thermal data and the detector output."""
import numpy as np
import pytest

from conftest import make_engine, run, ticks


def grid(e):
    return np.array(e.last_result["thermal"]["grid"])


def test_background_temperature_control_moves_the_grid(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "custom", auto=False)
        t0 = grid(e).mean()
        e.update_params({"background_temp_C": 55.0}); await ticks(e, 1)
        assert grid(e).mean() - t0 == pytest.approx(15.0, abs=1.0)
        assert e.last_result["panel_temp_C"] == pytest.approx(grid(e).mean(), abs=0.01)
    run(go())


def test_hotspot_controls_peak_area_and_position(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "custom", auto=False)
        assert e.last_result["thermal"]["hotspot_detected"] == "NO"

        # 1 pixel at 60 C: below absolute threshold and fewer than 2 hot pixels -> NO
        e.update_params({"hotspot_enabled": True, "hotspot_peak_C": 60, "hotspot_pixels": 1}); await ticks(e, 1)
        assert e.last_result["thermal"]["hotspot_detected"] == "NO"
        assert grid(e)[2, 2] == pytest.approx(60, abs=0.01)

        # 1 pixel at 70 C -> absolute rule
        e.update_params({"hotspot_peak_C": 70}); await ticks(e, 1)
        t = e.last_result["thermal"]
        assert t["hotspot_detected"] == "YES" and t["cond_abs_triggered"] and t["max_temp_C"] == pytest.approx(70, abs=0.01)
        assert [2, 2] in t["hot_pixels"]

        # 4 pixels at 62 C -> delta rule only, and a larger area means more contributing pixels
        e.update_params({"hotspot_peak_C": 62, "hotspot_pixels": 4}); await ticks(e, 1)
        t = e.last_result["thermal"]
        assert t["hotspot_detected"] == "YES" and t["cond_delta_triggered"] and not t["cond_abs_triggered"]
        assert t["hot_pixel_count"] >= 2

        # move it: the contributing pixels follow
        e.update_params({"hotspot_row": 5, "hotspot_col": 1}); await ticks(e, 1)
        assert [5, 1] in e.last_result["thermal"]["hot_pixels"]
        assert e.last_result["thermal"]["hotspot_row"] == 5

        # switch off -> cleared
        e.update_params({"hotspot_enabled": False}); await ticks(e, 1)
        assert e.last_result["thermal"]["hotspot_detected"] == "NO"
        assert any(ev["type"] == "HOTSPOT" and ev["message"] == "Hotspot cleared." for ev in e.events)
    run(go())


def test_detector_threshold_change_applies_live(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "hotspot", auto=False)
        assert e.last_result["thermal"]["hotspot_detected"] == "YES"
        e.update_config({"hotspot_abs_thresh_c": 120, "hotspot_delta_thresh_c": 90}); await ticks(e, 1)
        assert e.last_result["thermal"]["hotspot_detected"] == "NO"
    run(go())


def test_irradiance_changes_both_power_and_expected_power(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "healthy", auto=False)
        p0, x0 = e.last_result["electrical"]["power_W"], e.last_result["twin"]["power_expected_W"]
        e.update_params({"irradiance_Wm2": 450}); await ticks(e, 1)
        assert e.last_result["electrical"]["power_W"] < 0.6 * p0
        assert e.last_result["twin"]["power_expected_W"] < 0.6 * x0
        assert e.last_result["decision"]["ml_class"] == "Healthy_Clean"   # low light alone is not a fault
    run(go())


def test_invalid_parameters_are_rejected(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "custom", auto=False)
        for bad in ({"hotspot_pixels": 99}, {"soiling_level": 2}, {"bogus": 1}):
            with pytest.raises(ValueError):
                e.update_params(bad)
    run(go())
