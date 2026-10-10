"""Message bus: local fallback and a REAL MQTT round-trip against an embedded test broker.

The broker used in tests is `amqtt` (pure Python, test-only dependency). In the demo you would use
Mosquitto instead. If amqtt is not installed the broker tests are SKIPPED, not faked.
"""
import asyncio
import json
import socket

import pytest

from conftest import FAST, make_engine, messages, run
from app.config import SimConfig
from app.engine import SimulationEngine
from app.mqtt_link import MqttLink
from app.topics import TOPIC_COMMAND, TOPIC_DATA, TOPIC_FEEDBACK, TOPIC_STATUS

ENVELOPE_KEYS = {"schema_version", "panel_id", "type", "is_simulated", "seq", "sim_time", "timestamp"}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_local_mode_when_no_broker_is_reachable(tmp_path):
    async def go():
        link = MqttLink(host="127.0.0.1", port=free_port())          # nothing listens here
        e = SimulationEngine(config=_fast_cfg(), models_dir=tmp_path, mqtt=link)
        await e.start()
        e.playing = False
        await asyncio.sleep(0.5)
        assert link.connected is False and e.mqtt_status()["mode"] == "local_simulation"
        e.tick(); await asyncio.sleep(0.05)
        assert e.last_result is not None                              # still works, in local mode
        assert e.bus.transport == "local"
        await e.stop()
    run(go())


def test_mqtt_disabled_flag(tmp_path):
    async def go():
        link = MqttLink(enabled=False)
        e = SimulationEngine(config=_fast_cfg(), models_dir=tmp_path, mqtt=link)
        await e.start(); e.playing = False
        assert e.mqtt_status()["connected"] is False and "disabled" in e.mqtt_status()["last_error"]
        await e.stop()
    run(go())


def _fast_cfg():
    c = SimConfig(); c.update(FAST); return c


def test_every_topic_uses_the_common_json_envelope(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "soiled")
        from conftest import ticks
        await ticks(e, 6)
        for topic in (TOPIC_DATA, TOPIC_STATUS, TOPIC_COMMAND, TOPIC_FEEDBACK):
            msgs = messages(e, topic)
            assert msgs, topic
            for m in msgs:
                assert ENVELOPE_KEYS <= set(m), (topic, ENVELOPE_KEYS - set(m))
                assert m["schema_version"] == "1.0" and m["is_simulated"] is True
                json.dumps(m)                                         # strictly JSON-serialisable (no NaN)
        d = messages(e, TOPIC_DATA)[0]
        assert {"ina219", "bh1750", "amg8833", "actuators"} <= set(d)
        assert len(d["amg8833"]["grid"]) == 8 and len(d["amg8833"]["grid"][0]) == 8
        s = messages(e, TOPIC_STATUS)[0]
        assert {"ml_class", "hotspot", "final_status", "recommended_action", "underlying_action"} <= set(s)
    run(go())


def test_malformed_telemetry_is_reported_not_swallowed(tmp_path):
    async def go():
        e = await make_engine(tmp_path, "healthy")
        e.bus.publish(TOPIC_DATA, {"type": "telemetry", "ina219": {"voltage_V": 1}})   # missing fields
        await e.wait_idle()
        assert any(ev["type"] == "ERROR" and "Malformed telemetry" in ev["message"] for ev in e.events)
    run(go())


import importlib.util

needs_broker = pytest.mark.skipif(importlib.util.find_spec("amqtt") is None,
                                  reason="amqtt (embedded test broker) not installed - real-broker tests skipped")


async def _start_broker(port):
    from amqtt.broker import Broker
    cfg = {"listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{port}"}}, "sys_interval": 0,
           "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]}, "topic-check": {"enabled": False}}
    b = Broker(cfg)
    await b.start()
    return b


async def _wait(pred, timeout=8.0):
    end = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < end:
        if pred():
            return True
        await asyncio.sleep(0.05)
    return False


@needs_broker
def test_real_broker_round_trip_runs_the_whole_workflow(tmp_path):
    """Telemetry -> decision -> command -> feedback -> verification, every hop through the broker."""
    async def go():
        port = free_port()
        broker = await _start_broker(port)
        try:
            link = MqttLink(host="127.0.0.1", port=port)
            e = SimulationEngine(config=_fast_cfg(), models_dir=tmp_path, mqtt=link)
            e.captured = []
            e.bus.tap(lambda t, d, tr: e.captured.append((t, d, tr)))
            await e.start()
            e.playing = False
            assert await _wait(lambda: link.connected), "did not connect to broker"
            assert e.mqtt_status()["mode"] == "mqtt_broker"
            assert any(ev["type"] == "MQTT" and ev["level"] == "success" for ev in e.events) or await _wait(
                lambda: any(ev["type"] == "MQTT" for ev in e.events))

            e.select_scenario("soiled")
            for _ in range(3):
                e.tick(); await asyncio.sleep(0.15)
            assert await _wait(lambda: e.last_verification is None and any(t == TOPIC_FEEDBACK and d["state"] == "COMPLETED" for t, d, _ in e.captured))
            for _ in range(3):
                e.tick(); await asyncio.sleep(0.15)
            assert await _wait(lambda: e.last_verification is not None)
            assert e.last_verification["verdict"] == "RECOVERED"

            # every message really travelled through the broker, none through the local path
            assert e.captured and {tr for _, _, tr in e.captured} == {"mqtt"}
            assert {t for t, _, _ in e.captured} >= {TOPIC_DATA, TOPIC_STATUS, TOPIC_COMMAND, TOPIC_FEEDBACK}
            await e.stop()
        finally:
            await broker.shutdown()
    run(go())


@needs_broker
def test_external_client_can_inject_telemetry_and_observe_status(tmp_path):
    """A second MQTT client (stand-in for a future ESP32/sensor node) talks to the backend via the broker."""
    async def go():
        import paho.mqtt.client as mqtt
        port = free_port()
        broker = await _start_broker(port)
        try:
            link = MqttLink(host="127.0.0.1", port=port)
            e = SimulationEngine(config=_fast_cfg(), models_dir=tmp_path, mqtt=link)
            await e.start(); e.playing = False
            assert await _wait(lambda: link.connected)
            e.select_scenario("healthy")                        # builds a valid telemetry template
            await asyncio.sleep(0.3)

            seen = []
            c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            c.on_message = lambda cl, u, m: seen.append((m.topic, json.loads(m.payload)))
            c.connect("127.0.0.1", port); c.subscribe(TOPIC_STATUS); c.loop_start()
            await asyncio.sleep(0.3)

            tel = e.world.read()
            tel["amg8833"]["grid"][4][4] = 90.0                 # inject a hot pixel externally
            c.publish(TOPIC_DATA, json.dumps({"type": "telemetry", "seq": 999, "sim_time": "2026-01-01T09:00:00", **tel}))
            assert await _wait(lambda: any(d.get("seq") == 999 for _, d in seen))
            status = [d for _, d in seen if d.get("seq") == 999][0]
            assert status["hotspot"] == "YES" and status["max_temp_C"] == 90.0
            c.loop_stop(); await e.stop()
        finally:
            await broker.shutdown()
    run(go())
