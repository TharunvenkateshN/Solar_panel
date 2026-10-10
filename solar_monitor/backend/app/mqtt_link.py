"""Real MQTT client (paho-mqtt) with automatic reconnect.

If the broker is unreachable the link simply reports connected=False and the bus falls back
to in-process delivery. Start Mosquitto later and the link connects on its own.
"""
from __future__ import annotations

import os
import threading
from typing import Callable

from .topics import TOPIC_WILDCARD

try:
    import paho.mqtt.client as mqtt
    PAHO_ERROR = None
except Exception as e:  # noqa: BLE001
    mqtt = None
    PAHO_ERROR = f"paho-mqtt not importable: {e}"


class MqttLink:
    def __init__(self, host: str | None = None, port: int | None = None, enabled: bool | None = None):
        self.host = host or os.environ.get("MQTT_HOST", "127.0.0.1")
        self.port = int(port or os.environ.get("MQTT_PORT", 1883))
        env_enabled = os.environ.get("MQTT_ENABLED", "1") not in ("0", "false", "False")
        self.enabled = env_enabled if enabled is None else enabled
        self._connected = False
        self.last_error: str | None = PAHO_ERROR if self.enabled else None
        self._client = None
        self._on_message: Callable[[str, bytes], None] | None = None
        self._on_status: Callable[[dict], None] | None = None
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return self._connected

    def status(self) -> dict:
        return {
            "enabled": self.enabled, "connected": self._connected,
            "host": self.host, "port": self.port,
            "mode": "mqtt_broker" if self._connected else "local_simulation",
            "last_error": self.last_error,
        }

    def start(self, on_message: Callable[[str, bytes], None], on_status: Callable[[dict], None]) -> None:
        self._on_message, self._on_status = on_message, on_status
        if not self.enabled:
            self.last_error = "MQTT disabled (MQTT_ENABLED=0)"
            return
        if mqtt is None:
            return
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="solar-monitor-backend")
        client.reconnect_delay_set(min_delay=1, max_delay=5)
        client.on_connect = self._handle_connect
        client.on_disconnect = self._handle_disconnect
        client.on_message = lambda c, u, m: self._on_message(m.topic, m.payload)
        client.on_connect_fail = self._handle_fail
        self._client = client
        client.connect_async(self.host, self.port, keepalive=20)
        client.loop_start()

    def stop(self) -> None:
        if self._client is not None:
            try:
                self._client.disconnect()
                self._client.loop_stop()
            except Exception:  # noqa: BLE001
                pass
        self._connected = False

    def publish(self, topic: str, text: str) -> bool:
        if not self._connected or self._client is None:
            return False
        try:
            info = self._client.publish(topic, text, qos=0)
            return info.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:  # noqa: BLE001
            self.last_error = f"publish failed: {e}"
            return False

    # -- callbacks (paho thread) -------------------------------------------------
    def _handle_connect(self, client, userdata, flags, reason_code, properties=None):
        if getattr(reason_code, "is_failure", False):
            self.last_error = f"connect refused: {reason_code}"
            return
        client.subscribe(TOPIC_WILDCARD, qos=0)
        self._connected = True
        self.last_error = None
        self._notify()

    def _handle_disconnect(self, client, userdata, flags, reason_code=None, properties=None):
        was = self._connected
        self._connected = False
        if was:
            self.last_error = f"disconnected: {reason_code}"
            self._notify()

    def _handle_fail(self, client, userdata):
        msg = f"cannot reach broker at {self.host}:{self.port}"
        if self.last_error != msg:
            self.last_error = msg
            self._notify()

    def _notify(self):
        if self._on_status:
            self._on_status(self.status())
