"""Cleaning / tilting workflows, feedback, post-action verification (honest PASS and FAIL)."""
import asyncio

from conftest import make_engine, messages, run, ticks
from app.topics import TOPIC_COMMAND, TOPIC_FEEDBACK


def states(e):
    return [m["state"] for m in messages(e, TOPIC_FEEDBACK)]


def test_soiling_triggers_cleaning_then_verification_passes(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "soiled")
        await ticks(e, 6)
        cmds = messages(e, TOPIC_COMMAND)
        assert [c["command"] for c in cmds] == ["START_CLEANING"]
        assert cmds[0]["source"] == "decision_engine" and cmds[0]["is_simulated"] is True
        assert states(e)[0] == "STARTED" and states(e)[-1] == "COMPLETED"
        assert e.world.cleaned_fraction == 1.0

        v = e.last_verification
        assert v and v["action"] == "START_CLEANING" and v["verdict"] == "RECOVERED"
        assert v["pre"]["deviation"] > 10 > v["post"]["deviation"]
        assert v["post"]["power"] > v["pre"]["power"] and v["power_gain_W"] > 0
        assert e.last_result["decision"]["ml_class"] == "Healthy_Clean"
        types = [ev["type"] for ev in e.events]
        assert "COMMAND" in types and "ACTION" in types and "VERIFY" in types
    run(go())


def test_cleaning_that_does_not_work_is_reported_as_failed_and_not_retried(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "soiled", cleaning_effectiveness=0.1)
        await ticks(e, 12)
        v = e.last_verification
        assert v["verdict"] == "NOT_RECOVERED" and v["post"]["deviation"] > 10
        assert len(messages(e, TOPIC_COMMAND)) == 1            # no endless retry loop
        assert any("auto-retry suppressed" in ev["message"] for ev in e.events)
        assert any(ev["type"] == "VERIFY" and ev["level"] == "error" and "Not claiming success" in ev["message"] for ev in e.events)
        stage = {s["id"]: s for s in e.stages()}["verification"]
        assert stage["state"] == "error"
        # operator can retry; with a better cleaner it now passes
        e.update_config({"cleaning_effectiveness": 1.0})
        ok, _ = e.send_command("START_CLEANING", "operator")
        assert ok
        await e.wait_idle(); await ticks(e, 3)
        assert e.last_verification["verdict"] == "RECOVERED"
    run(go())


def test_partial_shading_triggers_tilt_and_power_recovers(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "shading")
        await ticks(e, 5)
        cmds = messages(e, TOPIC_COMMAND)
        assert [c["command"] for c in cmds] == ["TILT_PANEL"]       # tilt, never cleaning
        assert cmds[0]["target_angle_deg"] == 120.0
        fb = messages(e, TOPIC_FEEDBACK)
        assert fb[-1]["state"] == "COMPLETED" and fb[-1]["angle_deg"] == 120.0
        assert e.world.tilt_angle_deg == 120.0
        v = e.last_verification
        assert v["action"] == "TILT_PANEL" and v["verdict"] == "RECOVERED"
        assert v["pre"]["deviation"] > 20 and v["post"]["deviation"] < 10
        assert e.last_result["actuators"]["tilt_angle_deg"] == 120.0
    run(go())


def test_ineffective_tilt_fails_verification(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "shading", tilt_efficacy=0.1)
        await ticks(e, 8)
        assert e.last_verification["verdict"] == "NOT_RECOVERED"
        assert len(messages(e, TOPIC_COMMAND)) == 1
    run(go())


def test_tilt_moves_in_steps(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "shading", tilt_step_deg=10.0)
        await ticks(e, 2)
        angles = [m["angle_deg"] for m in messages(e, TOPIC_FEEDBACK)]
        assert angles == sorted(angles) and angles[0] == 90.0 and angles[-1] == 120.0 and len(set(angles)) >= 3
    run(go())


def test_hotspot_scenarios_raise_alert_but_never_auto_actuate(tmp_path):
    async def go():
        for sid in ("hotspot", "soiled_hotspot", "shading_hotspot"):
            e = await make_engine(tmp_path, sid)
            await ticks(e, 6)
            assert messages(e, TOPIC_COMMAND) == [], sid
            assert any(ev["type"] == "HOTSPOT" and ev["level"] == "alert" for ev in e.events), sid
            st = {s["id"]: s for s in e.stages()}
            assert st["action"]["state"] == "alert" and st["hotspot"]["state"] == "alert"
    run(go())


def test_manual_cleaning_on_shaded_panel_does_not_claim_success(tmp_path):
    """Cleaning is the wrong remedy for shading: the verification must say so."""
    async def go():
        e = await make_engine(tmp_path, "shading", auto=False)
        ok, _ = e.send_command("START_CLEANING", "operator")
        assert ok
        await e.wait_idle(); await ticks(e, 3)
        assert e.last_verification["verdict"] == "NOT_RECOVERED"
        assert abs(e.last_verification["power_gain_pct"]) < 5
    run(go())


def test_second_command_is_refused_while_busy(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "soiled", auto=False, cleaning_duration_s=1.0)
        assert e.send_command("START_CLEANING", "operator")[0]
        assert not e.send_command("TILT_PANEL", "operator")[0]
        assert not e.send_command("FLY", "operator")[0]
        await e.wait_idle()
    run(go())


def test_auto_execute_off_waits_for_operator(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "soiled", auto=False)
        await ticks(e, 5)
        assert messages(e, TOPIC_COMMAND) == []
        assert {s["id"]: s for s in e.stages()}["action"]["headline"] == "Awaiting operator"
    run(go())


def test_no_feedback_means_no_verification_and_a_visible_timeout(tmp_path):
    """Actuator simulator disabled and no real hardware answering: nothing is claimed."""
    async def go():
        async def drain():
            while e.bus.pending:
                await asyncio.sleep(0)
            await asyncio.sleep(0)
        e = await make_engine(tmp_path, "soiled", actuator_simulator_enabled=False, command_timeout_s=1)
        for _ in range(3):
            e.tick(); await drain()
        assert len(messages(e, TOPIC_COMMAND)) == 1
        assert e.last_verification is None and e.world.cleaned_fraction == 0.0
        e.inflight["t0"] -= 5
        e.tick(); await drain()
        assert any("No feedback" in ev["message"] for ev in e.events)
    run(go())


def test_scenario_change_cancels_running_action(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "soiled", auto=False, cleaning_duration_s=1.0)
        e.send_command("START_CLEANING", "operator")
        await ticks(e, 1)
        e.select_scenario("healthy")
        await e.wait_idle()
        assert e.pending_verification is None and e.last_verification is None and not e.world.cleaning_active
    run(go())


def test_before_baseline_only_uses_readings_from_the_current_situation(tmp_path):
    """Switching scenario must not leak the previous scenario's readings into the 'before' numbers."""
    async def go():
        e = await make_engine(tmp_path, "healthy")
        await ticks(e, 4)                                  # healthy history (deviation ~ 2%)
        e.select_scenario("shading")                       # tilt is commanded on the first shaded reading
        await e.wait_idle(); await ticks(e, 3)
        v = e.last_verification
        assert v["action"] == "TILT_PANEL" and v["pre"]["n"] == 1
        assert v["pre"]["deviation"] > 20, v["pre"]
    run(go())
