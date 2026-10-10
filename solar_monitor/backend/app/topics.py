"""MQTT topic names and the shared JSON envelope (schema_version 1.0)."""
from __future__ import annotations

import datetime

TOPIC_DATA = "solar/panel/data"          # sensor telemetry
TOPIC_STATUS = "solar/panel/status"      # classification, hotspot, final state
TOPIC_COMMAND = "solar/panel/command"    # START_CLEANING / TILT_PANEL
TOPIC_FEEDBACK = "solar/panel/feedback"  # actuator feedback
TOPIC_WILDCARD = "solar/panel/#"

PANEL_ID = "panel_1"
SCHEMA_VERSION = "1.0"


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def envelope(msg_type: str, seq: int, sim_time: str, body: dict, is_simulated: bool = True) -> dict:
    """Common header for every message on every topic."""
    return {
        "schema_version": SCHEMA_VERSION,
        "panel_id": PANEL_ID,
        "type": msg_type,
        "is_simulated": is_simulated,
        "seq": seq,
        "sim_time": sim_time,
        "timestamp": utc_now(),
        **body,
    }
