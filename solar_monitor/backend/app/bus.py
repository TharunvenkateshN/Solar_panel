"""Message bus: every inter-component message goes through `publish`.

* Broker connected  -> the message is published to the MQTT broker and delivered back to
                       subscribers by the broker round-trip (transport = "mqtt").
* Broker unavailable -> delivered in-process (transport = "local"). The UI shows this mode
                       explicitly; it is never presented as MQTT.
"""
from __future__ import annotations

import asyncio
import json
import math
from typing import Callable

import numpy as np


def clean(obj):
    """Make an object JSON-safe: numpy -> python, NaN/Inf -> None."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return clean(obj.tolist())
    if isinstance(obj, np.generic):
        return clean(obj.item())
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    return obj


class MessageBus:
    def __init__(self):
        self._subs: dict[str, list[Callable]] = {}
        self._taps: list[Callable] = []
        self.mqtt = None  # MqttLink | None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.pending = 0  # local messages queued but not yet delivered (used by tests)
        self.on_error: Callable[[str, Exception], None] = lambda topic, exc: None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def subscribe(self, topic: str, handler: Callable[[dict], None]) -> None:
        self._subs.setdefault(topic, []).append(handler)

    def tap(self, fn: Callable[[str, dict, str], None]) -> None:
        """Observe every delivered message (used to feed the UI's MQTT monitor)."""
        self._taps.append(fn)

    @property
    def transport(self) -> str:
        return "mqtt" if (self.mqtt is not None and self.mqtt.connected) else "local"

    def publish(self, topic: str, payload: dict) -> str:
        data = clean(payload)
        if self.mqtt is not None and self.mqtt.connected:
            if self.mqtt.publish(topic, json.dumps(data)):
                return "mqtt"
        self.pending += 1
        loop = self.loop or asyncio.get_running_loop()
        loop.call_soon(self._deliver_local, topic, data)
        return "local"

    def _deliver_local(self, topic: str, data: dict) -> None:
        try:
            self._deliver(topic, data, "local")
        finally:
            self.pending -= 1

    # called from paho's network thread
    def on_mqtt_message(self, topic: str, raw: bytes) -> None:
        try:
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("payload is not a JSON object")
        except Exception as e:
            if self.loop:
                self.loop.call_soon_threadsafe(self.on_error, topic, e)
            return
        if self.loop:
            self.loop.call_soon_threadsafe(self._deliver, topic, data, "mqtt")

    def _deliver(self, topic: str, data: dict, transport: str) -> None:
        for tap in self._taps:
            try:
                tap(topic, data, transport)
            except Exception as e:  # noqa: BLE001
                self.on_error(topic, e)
        for handler in self._subs.get(topic, []):
            try:
                handler(data)
            except Exception as e:  # noqa: BLE001
                self.on_error(topic, e)
