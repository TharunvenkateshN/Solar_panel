"""REST + WebSocket API, as the frontend uses it."""
import pytest
from fastapi.testclient import TestClient

from app.config import SimConfig
from app.engine import SimulationEngine
from app.main import create_app
from conftest import FAST


@pytest.fixture
def client(tmp_path):
    cfg = SimConfig(); cfg.update({**FAST, "tick_interval_s": 30})
    engine = SimulationEngine(config=cfg, models_dir=tmp_path)           # no MQTT link -> local mode
    with TestClient(create_app(engine)) as c:
        c.post("/api/sim/pause")
        yield c


def test_state_endpoint_describes_the_whole_system(client):
    s = client.get("/api/state").json()
    assert len(s["scenarios"]) == 8 and s["scenario_id"] == "healthy"
    assert s["classifier"]["mode"] == "simulated" and s["mqtt"]["mode"] == "local_simulation"
    assert s["config"]["persist_cycles"] == 3 and s["config"]["soiling_dev_thresh_pct"] == 10.0


def test_select_scenario_runs_the_pipeline(client):
    assert client.post("/api/scenario/soiled").status_code == 200
    s = client.get("/api/state").json()
    assert s["scenario_id"] == "soiled"
    assert s["result"]["decision"]["ml_class"] == "Soiling_Dusty"
    assert len(s["result"]["stages"]) == 8
    assert client.post("/api/scenario/nope").status_code == 422


def test_params_change_the_derived_result(client):
    client.post("/api/scenario/custom")
    r = client.put("/api/params", json={"hotspot_enabled": True, "hotspot_peak_C": 85, "hotspot_pixels": 3})
    assert r.status_code == 200
    client.post("/api/sim/step")
    s = client.get("/api/state").json()
    assert s["result"]["thermal"]["hotspot_detected"] == "YES"
    assert s["scenario_label"].endswith("(modified)")
    assert client.put("/api/params", json={"soiling_level": 5}).status_code == 422


def test_config_update_and_validation(client):
    assert client.put("/api/config", json={"persist_cycles": 2}).json()["config"]["persist_cycles"] == 2
    assert client.put("/api/config", json={"persist_cycles": 0}).status_code == 422
    assert client.put("/api/config", json={"bogus": 1}).status_code == 422


def test_manual_command_and_conflict(client):
    client.post("/api/scenario/soiled")
    client.put("/api/config", json={"auto_execute": False, "cleaning_duration_s": 2})
    assert client.post("/api/command/START_CLEANING").status_code == 200
    assert client.post("/api/command/TILT_PANEL").status_code == 409
    assert client.post("/api/command/FLY").status_code == 409


def test_websocket_sends_snapshot_then_live_updates(client):
    with client.websocket_connect("/ws") as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot" and snap["result"] is not None
        client.post("/api/scenario/hotspot")
        kinds, tick = set(), None
        for _ in range(60):
            m = ws.receive_json()
            kinds.add(m["type"])
            if m["type"] == "tick":
                tick = m
                break
        assert tick and tick["result"]["thermal"]["hotspot_detected"] == "YES"
        assert {"scenario", "bus"} <= kinds


def test_reset_clears_history(client):
    client.post("/api/sim/step"); client.post("/api/sim/step")
    client.post("/api/sim/reset")
    s = client.get("/api/state").json()
    assert s["sim"]["tick"] == 1 and len(s["history"]) == 1


def test_classifier_reload_endpoint(client):
    assert client.post("/api/classifier/reload").json()["mode"] == "simulated"


def test_websocket_streams_world_truth_during_an_action(client):
    """The 3D view needs tilt/dust/shade to follow the actuator while it moves."""
    client.put("/api/config", json={"auto_execute": False, "tilt_step_s": 0.05, "tilt_step_deg": 10})
    client.post("/api/scenario/shading")
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        assert client.post("/api/command/TILT_PANEL").status_code == 200
        angles, shades = [], []
        for _ in range(200):
            m = ws.receive_json()
            if m["type"] == "truth":
                angles.append(m["truth"]["tilt_angle_deg"]); shades.append(m["truth"]["effective_shading"])
            if m["type"] == "action" and m["action"]["phase"] == "completed":
                break
        assert angles[0] < angles[-1] == 120.0
        assert shades[-1] < shades[0]            # shadow shrinks as the panel tilts


def test_event_endpoint_and_catalog(client):
    state = client.get("/api/state").json()
    assert {e["id"] for e in state["event_catalog"]} >= {"clean", "tilt", "rain", "cloud", "dust_storm", "night", "hotspot_on"}
    client.put("/api/config", json={"event_time_scale": 5})
    r = client.post("/api/event/cloud")
    assert r.status_code == 200 and r.json()["message"] == "Passing cloud"
    t = client.get("/api/state").json()["truth"]
    assert t["weather"]["cloud"] is True and t["effects"]
    assert client.post("/api/event/nope").status_code == 422
    assert client.post("/api/event/tilt", json={"params": {"angle": 999}}).status_code == 422
    client.put("/api/config", json={"auto_execute": False, "cleaning_duration_s": 2})
    assert client.post("/api/event/clean").status_code == 200
    assert client.post("/api/event/tilt", json={"params": {"angle": 100}}).status_code == 409


def test_cors_is_off_by_default_and_allows_only_configured_origins(tmp_path, monkeypatch):
    def make():
        cfg = SimConfig(); cfg.update({**FAST, "tick_interval_s": 30})
        return TestClient(create_app(SimulationEngine(config=cfg, models_dir=tmp_path)))

    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    with make() as c:
        r = c.get("/api/health", headers={"Origin": "https://app.vercel.app"})
        assert "access-control-allow-origin" not in r.headers

    monkeypatch.setenv("CORS_ORIGINS", "https://app.vercel.app/, https://other.example")
    with make() as c:
        ok = c.get("/api/health", headers={"Origin": "https://app.vercel.app"})
        assert ok.headers["access-control-allow-origin"] == "https://app.vercel.app"
        bad = c.get("/api/health", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in bad.headers
        pre = c.options("/api/scenario/soiled", headers={"Origin": "https://app.vercel.app", "Access-Control-Request-Method": "POST"})
        assert pre.status_code == 200 and "POST" in pre.headers["access-control-allow-methods"]
