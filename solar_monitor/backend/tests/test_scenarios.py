"""Each preset must produce the expected result through the real pipeline (no hard-coded labels)."""
import pytest

from conftest import make_engine, messages, run, ticks
from app.scenarios import SCENARIOS
from app.topics import TOPIC_DATA, TOPIC_STATUS

# scenario -> (ml_class, hotspot, final_status, action) expected once the decision has settled
EXPECTED = {
    "healthy": ("Healthy_Clean", "NO", "HEALTHY", "NO_ACTION"),
    "soiled": ("Soiling_Dusty", "NO", "CLEANING_REQUIRED", "START_CLEANING"),
    "shading": ("Partial_Shading", "NO", "PARTIAL_SHADING", "TILT_PANEL"),
    "hotspot": ("Healthy_Clean", "YES", "HOTSPOT_DETECTED", "HOTSPOT_ALERT"),
    "soiled_hotspot": ("Soiling_Dusty", "YES", "HOTSPOT_AND_SOILING", "HOTSPOT_ALERT_WITH_SOILING"),
    "shading_hotspot": ("Partial_Shading", "YES", "HOTSPOT_AND_PARTIAL_SHADING", "HOTSPOT_ALERT_WITH_PARTIAL_SHADING"),
    "soiled_shaded": ("Partial_Shading", "NO", "PARTIAL_SHADING_AND_SOILING", "TILT_PANEL"),
    "post_cleaning": ("Healthy_Clean", "NO", "HEALTHY", "NO_ACTION"),
    "custom": ("Healthy_Clean", "NO", "HEALTHY", "NO_ACTION"),
}


def test_every_scenario_has_an_expectation():
    assert set(EXPECTED) == set(SCENARIOS)
    assert len(SCENARIOS) == 9


@pytest.mark.parametrize("sid", list(EXPECTED))
def test_scenario_pipeline_output(tmp_path, sid):
    async def go():
        e = await make_engine(tmp_path, sid, auto=False)   # auto off: observe pure decisions
        await ticks(e, 4)                                  # 5 readings -> persistence satisfied
        r = e.last_result
        ml, hs, status, action = EXPECTED[sid]
        assert r["decision"]["ml_class"] == ml
        assert r["thermal"]["hotspot_detected"] == hs
        assert r["decision"]["final_status"] == status
        assert r["decision"]["recommended_action"] == action
        assert r["ml"]["mode"] == "simulated" and r["ml"]["confidence"] is None
        # the published status message matches what the pipeline computed
        st = messages(e, TOPIC_STATUS)[-1]
        assert (st["ml_class"], st["hotspot"], st["final_status"], st["recommended_action"]) == (ml, hs, status, action)
        assert len(messages(e, TOPIC_DATA)) == 5
    run(go())


def test_soiling_waits_two_cycles_then_requests_cleaning(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "soiled", auto=False)
        await ticks(e, 3)
        actions = [p["action"] for p in e.history]
        assert actions[:4] == ["WAIT", "WAIT", "START_CLEANING", "START_CLEANING"]
        assert all(p["deviation"] > 10 for p in e.history)
    run(go())


def test_shading_requests_tilt_immediately_and_never_cleaning(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "shading", auto=False)
        assert e.history[0]["action"] == "TILT_PANEL"
        assert e.last_result["decision"]["base_action"] != "START_CLEANING"
    run(go())


def test_hotspot_alert_does_not_erase_ml_class(tmp_path):
    async def go():
        for plain, hot in (("healthy", "hotspot"), ("soiled", "soiled_hotspot"), ("shading", "shading_hotspot")):
            a = await make_engine(tmp_path, plain, auto=False)
            b = await make_engine(tmp_path, hot, auto=False)
            assert a.last_result["decision"]["ml_class"] == b.last_result["decision"]["ml_class"]
            assert a.last_result["thermal"]["hotspot_detected"] == "NO"
            assert b.last_result["thermal"]["hotspot_detected"] == "YES"
    run(go())


def test_scenarios_are_deterministic_for_a_seed(tmp_path):
    async def go():
        a = await make_engine(tmp_path, "soiled", auto=False)
        b = await make_engine(tmp_path, "soiled", auto=False)
        await ticks(a, 3); await ticks(b, 3)
        assert [p["power"] for p in a.history] == [p["power"] for p in b.history]
    run(go())


def test_pipeline_output_follows_the_data_not_the_scenario_label(tmp_path):
    """Custom scenario: dirtying the panel changes the derived class with no label involved."""
    async def go():
        e = await make_engine(tmp_path, "custom", auto=False)
        assert e.last_result["decision"]["ml_class"] == "Healthy_Clean"
        e.update_params({"soiling_level": 0.7}); await ticks(e, 1)
        assert e.last_result["decision"]["ml_class"] == "Soiling_Dusty"
        e.update_params({"soiling_level": 0.0, "shading_fraction": 0.4}); await ticks(e, 1)
        assert e.last_result["decision"]["ml_class"] == "Partial_Shading"
        e.update_params({"shading_fraction": 0.0}); await ticks(e, 1)
        assert e.last_result["decision"]["ml_class"] == "Healthy_Clean"
    run(go())


def test_energy_and_power_values_are_physically_consistent(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "soiled", auto=False)
        r = e.last_result
        el = r["electrical"]
        assert el["power_W"] == pytest.approx(el["voltage_V"] * el["current_A"], rel=2e-3)
        assert r["twin"]["power_expected_W"] > el["power_W"]
        h = r["twin"]["health"]
        assert r["twin"]["health_score_pct"] == h["score"]
        assert h["score"] == pytest.approx(100 - sum(h["penalties"].values()), abs=0.2)
        assert h["score"] < 100 - r["twin"]["deviation_pct"] + 0.02   # soiling flag only ever lowers it
        assert r["twin"]["irradiance_source"] == "lux_derived_UNCALIBRATED"
    run(go())


@pytest.mark.parametrize("shade", [0.1, 0.3, 0.5, 0.65, 0.8, 0.9])
@pytest.mark.parametrize("hot", [None, (75, 4), (110, 16), (55, 16)])
def test_shading_is_recognised_at_any_shaded_fraction_and_hotspots_never_fake_it(tmp_path, shade, hot):
    """The cool-region feature must work when most of the panel is shaded, with or without a hotspot, and a
    large hotspot on an unshaded panel must not look like shading."""
    async def go():
        e = await make_engine(tmp_path, "custom", auto=False)
        params = {"shading_fraction": shade}
        if hot:
            params.update(hotspot_enabled=True, hotspot_peak_C=hot[0], hotspot_pixels=hot[1])
        e.update_params(params)
        await ticks(e, 2)
        assert e.last_result["decision"]["ml_class"] == "Partial_Shading", (shade, hot, e.last_result["features"]["derived"])
    run(go())


@pytest.mark.parametrize("hot", [(75, 1), (75, 4), (110, 16), (60, 9)])
def test_large_hotspot_on_an_unshaded_panel_is_not_classified_as_shading(tmp_path, hot):
    async def go():
        e = await make_engine(tmp_path, "custom", auto=False)
        e.update_params({"hotspot_enabled": True, "hotspot_peak_C": hot[0], "hotspot_pixels": hot[1]})
        await ticks(e, 2)
        assert e.last_result["decision"]["ml_class"] == "Healthy_Clean", (hot, e.last_result["features"]["derived"])
    run(go())
