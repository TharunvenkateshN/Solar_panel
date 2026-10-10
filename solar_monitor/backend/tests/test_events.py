"""Operator what-if events: each one must change the simulated data, and the pipeline must react correctly."""
import asyncio

import pytest

from conftest import make_engine, messages, run, ticks
from app.topics import TOPIC_COMMAND
from app.world_events import BY_ID, CATALOG

FASTEV = dict(event_time_scale=0.02)   # timed events take ~0.1-0.3 s


async def settle(e, timeout=5.0):
    """Wait until all timed events ended."""
    end = asyncio.get_running_loop().time() + timeout
    while e.events_runner.effects() and asyncio.get_running_loop().time() < end:
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.02)


def test_catalog_is_complete_and_well_formed():
    ids = [e.id for e in CATALOG]
    assert len(ids) == len(set(ids)) >= 14
    assert {e.category for e in CATALOG} == {"Corrective actions", "Weather & environment", "Time of day", "Faults & conditions"}
    for e in CATALOG:
        assert e.label and e.description and e.effect and e.kind in ("actuator", "timed", "instant")
        for p in e.params:
            assert p["min"] <= p["default"] <= p["max"]


def test_dust_storm_deposits_dust_and_turns_the_class_to_soiling(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "healthy", auto=False, **FASTEV)
        assert e.last_result["decision"]["ml_class"] == "Healthy_Clean"
        e.run_event("dust_storm")
        assert e.world.weather["dust_storm"] is True
        await settle(e)
        assert e.world.weather["dust_storm"] is False
        assert e.world.effective_soiling > 0.45
        await ticks(e, 1)
        assert e.last_result["decision"]["ml_class"] == "Soiling_Dusty"
        assert e.last_result["twin"]["deviation_pct"] > 10
    run(go())


def test_rain_washes_most_of_the_dust_and_restores_light(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "soiled", auto=False, **FASTEV)
        before = e.world.effective_soiling
        e.run_event("rain")
        assert e.world.irr_factor == pytest.approx(0.35)
        await settle(e)
        assert e.world.irr_factor == 1.0
        assert e.world.effective_soiling == pytest.approx(before * 0.29, rel=0.05)
        await ticks(e, 1)
        assert e.last_result["decision"]["ml_class"] == "Healthy_Clean"
    run(go())


def test_cloud_dims_power_and_expected_power_together_so_it_is_not_a_fault(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "healthy", auto=False, event_time_scale=5.0)   # long enough to sample
        p0, x0 = e.last_result["electrical"]["power_W"], e.last_result["twin"]["power_expected_W"]
        e.run_event("cloud")
        await ticks(e, 2)
        r = e.last_result
        assert r["electrical"]["power_W"] < 0.45 * p0 and r["twin"]["power_expected_W"] < 0.45 * x0
        assert abs(r["twin"]["deviation_pct"]) < 10
        assert r["decision"]["ml_class"] == "Healthy_Clean" and r["decision"]["recommended_action"] == "NO_ACTION"
        e.events_runner.cancel_all(); await asyncio.sleep(0.05)
        assert e.world.irr_factor == 1.0 and not e.world.weather["cloud"]
    run(go())


def test_heat_wave_warms_the_thermal_grid_without_a_hotspot(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "healthy", auto=False, event_time_scale=5.0)
        t0 = e.last_result["panel_temp_C"]
        e.run_event("heat_wave")
        await ticks(e, 1)
        assert e.last_result["panel_temp_C"] - t0 == pytest.approx(12, abs=1.5)
        assert e.last_result["thermal"]["hotspot_detected"] == "NO"
        e.events_runner.cancel_all(); await asyncio.sleep(0.05)
        assert e.world.temp_offset == 0
    run(go())


@pytest.mark.parametrize("ev,g", [("sunrise", 250), ("noon", 1000), ("dusk", 120), ("night", 0)])
def test_time_of_day_sets_irradiance_and_pipeline_stays_valid(tmp_path, ev, g):
    async def go():
        e = await make_engine(tmp_path, "healthy", auto=False)
        e.run_event(ev)
        await ticks(e, 2)
        assert e.world.params.irradiance_Wm2 == g
        r = e.last_result
        if g == 0:
            assert r["electrical"]["power_W"] == 0 and r["twin"]["deviation_pct"] is None     # undefined, not a fake number
            assert r["decision"]["recommended_action"] in ("NO_ACTION", "WAIT")
        else:
            assert r["electrical"]["power_W"] == pytest.approx(g / 1000 * 25, rel=0.25)
            assert r["decision"]["ml_class"] == "Healthy_Clean"
    run(go())


def test_obstruction_shadow_on_off(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "healthy", auto=False)
        e.run_event("shadow_on"); await ticks(e, 1)
        assert e.world.params.shading_fraction == pytest.approx(0.3)
        assert e.last_result["decision"]["ml_class"] == "Partial_Shading"
        e.run_event("shadow_off"); await ticks(e, 1)
        assert e.last_result["decision"]["ml_class"] == "Healthy_Clean"
    run(go())


def test_hotspot_inject_and_repair(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "soiled", auto=False)
        e.run_event("hotspot_on", {"params": {"peak": 90}} and {"peak": 90}); await ticks(e, 1)
        t = e.last_result["thermal"]
        assert t["hotspot_detected"] == "YES" and t["max_temp_C"] == pytest.approx(90, abs=0.1)
        assert e.last_result["decision"]["ml_class"] == "Soiling_Dusty"           # class preserved
        e.run_event("hotspot_off"); await ticks(e, 1)
        assert e.last_result["thermal"]["hotspot_detected"] == "NO"
        with pytest.raises(ValueError):
            e.run_event("hotspot_on", {"peak": 500})
    run(go())


def test_rotate_to_a_chosen_angle_is_commanded_and_reaches_it(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "healthy", auto=False)
        e.run_event("tilt", {"angle": 65})
        await e.wait_idle()
        cmd = messages(e, TOPIC_COMMAND)[-1]
        assert cmd["command"] == "TILT_PANEL" and cmd["target_angle_deg"] == 65 and cmd["source"] == "operator"
        assert e.world.tilt_angle_deg == 65
        e.run_event("flat"); await e.wait_idle()
        assert e.world.tilt_angle_deg == 90
        with pytest.raises(ValueError):
            e.run_event("tilt", {"angle": 400})
    run(go())


def test_rotating_a_healthy_panel_reports_no_change_instead_of_a_fake_recovery(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "healthy", auto=False)
        e.run_event("tilt", {"angle": 120}); await e.wait_idle(); await ticks(e, 3)
        assert e.last_verification["verdict"] == "NO_CHANGE"
        assert any("already within limits" in ev["message"] for ev in e.events)
    run(go())


def test_rotating_away_from_the_sun_makes_shading_worse_and_is_not_called_recovered(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "shading", auto=False)
        base = e.world.effective_shading
        e.run_event("tilt", {"angle": 60}); await e.wait_idle(); await ticks(e, 3)
        assert e.world.effective_shading > base * 1.5
        assert e.last_verification["verdict"] == "NOT_RECOVERED"
        e.run_event("tilt", {"angle": 120}); await e.wait_idle(); await ticks(e, 3)
        assert e.world.effective_shading < base * 0.3
        assert e.last_verification["verdict"] == "RECOVERED"
    run(go())


def test_actuator_events_are_refused_while_busy_but_weather_is_not(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "soiled", auto=False, cleaning_duration_s=1.0, event_time_scale=5.0)
        e.run_event("clean")
        with pytest.raises(RuntimeError):
            e.run_event("tilt", {"angle": 100})
        e.run_event("cloud")                                  # environment keeps evolving while the robot works
        assert e.world.weather["cloud"]
        e.events_runner.cancel_all()
        await e.wait_idle()
    run(go())


def test_scenario_change_cancels_timed_events_and_clears_modifiers(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "healthy", auto=False, event_time_scale=10.0)
        e.run_event("rain"); e.run_event("heat_wave")
        assert len(e.events_runner.effects()) == 2
        e.select_scenario("soiled"); await asyncio.sleep(0.1)
        assert e.events_runner.effects() == []
        assert e.world.irr_factor == 1.0 and e.world.temp_offset == 0 and not any(e.world.weather.values())
    run(go())


def test_overlapping_modifiers_combine_and_unwind_independently(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "healthy", auto=False, event_time_scale=10.0)
        e.run_event("rain"); e.run_event("cloud")
        assert e.world.irr_factor == pytest.approx(0.35 * 0.3)
        e.events_runner.cancel("rain")
        assert e.world.irr_factor == pytest.approx(0.3)
        e.events_runner.cancel_all(); await asyncio.sleep(0.05)
        assert e.world.irr_factor == 1.0
    run(go())


def test_truth_exposes_weather_and_active_effects_for_the_3d_view(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "healthy", auto=False, event_time_scale=10.0)
        e.run_event("cloud")
        t = e._truth()
        assert t["weather"]["cloud"] is True and t["irradiance_effective"] == pytest.approx(900 * 0.3, rel=0.01)
        assert t["effects"][0]["id"] == "cloud" and t["effects"][0]["remaining_s"] > 0
        e.events_runner.cancel_all(); await asyncio.sleep(0.05)
        assert e._truth()["weather"]["cloud"] is False
    run(go())


def test_every_catalog_event_can_be_run(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "custom", auto=False, **FASTEV)
        for ev in CATALOG:
            if ev.kind == "actuator":
                await e.wait_idle()
            e.run_event(ev.id)
            await ticks(e, 1)
            await settle(e)
        await e.wait_idle()
        assert e.last_result is not None
    run(go())
