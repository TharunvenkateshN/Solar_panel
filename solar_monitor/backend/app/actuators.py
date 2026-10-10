"""Software actuator simulator: listens on solar/panel/command, publishes solar/panel/feedback.

NOTHING here drives a real motor or servo. It animates a cleaning cycle / tilt move over time,
changes the virtual panel's state when the action completes, and reports progress as feedback.
Disable it (config.actuator_simulator_enabled = false) if real hardware answers on the
feedback topic instead.

Recovery models are SIMULATION ASSUMPTIONS (see world.py / config.py), not measurements.
"""
from __future__ import annotations

import asyncio
from typing import Callable

from .bus import MessageBus
from .config import SimConfig
from .topics import TOPIC_FEEDBACK, envelope
from .world import PanelWorld

CLEANING, TILT = "START_CLEANING", "TILT_PANEL"
SUPPORTED = (CLEANING, TILT)


class ActuatorSimulator:
    def __init__(self, bus: MessageBus, world: PanelWorld, config: SimConfig,
                 sim_time: Callable[[], tuple[int, str]]):
        self.bus, self.world, self.config = bus, world, config
        self._sim_time = sim_time
        self.busy = False
        self._task: asyncio.Task | None = None

    def on_command(self, msg: dict) -> None:
        if not self.config.actuator_simulator_enabled:
            return
        action, cid = msg.get("command"), msg.get("command_id")
        if action not in SUPPORTED:
            self._feedback(cid, action or "UNKNOWN", "REJECTED", message=f"Unsupported command '{action}'")
            return
        if self.busy:
            self._feedback(cid, action, "REJECTED", message="Actuator busy")
            return
        self.busy = True
        runner = self._run_cleaning if action == CLEANING else self._run_tilt
        self._task = asyncio.get_running_loop().create_task(runner(msg))

    def cancel(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self.busy = False
        self.world.cleaning_active = False
        self.world.tilt_active = False

    async def wait_idle(self) -> None:
        if self._task:
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    # -- cleaning ------------------------------------------------------------------
    async def _run_cleaning(self, cmd: dict) -> None:
        cid, cfg = cmd.get("command_id"), self.config
        try:
            self.world.cleaning_active = True
            self._feedback(cid, CLEANING, "STARTED", progress=0, message="Cleaning mechanism activated (simulated)")
            steps = max(1, int(cfg.cleaning_duration_s / 0.5))
            for k in range(1, steps + 1):
                await asyncio.sleep(cfg.cleaning_duration_s / steps)
                if k < steps:
                    self._feedback(cid, CLEANING, "IN_PROGRESS", progress=round(100 * k / steps))
            self.world.apply_cleaning(cfg.cleaning_effectiveness)
            self.world.cleaning_active = False
            self._feedback(cid, CLEANING, "COMPLETED", progress=100,
                           message=f"Cleaning cycle finished (simulated, effectiveness {cfg.cleaning_effectiveness:.0%})")
        finally:
            self.world.cleaning_active = False
            self.busy = False

    # -- tilting -------------------------------------------------------------------
    async def _run_tilt(self, cmd: dict) -> None:
        cid, cfg = cmd.get("command_id"), self.config
        try:
            start = self.world.tilt_angle_deg
            target = float(cmd.get("target_angle_deg", cfg.tilt_target_angle_deg))
            target = min(180.0, max(0.0, target))
            self.world.tilt_active = True
            self._feedback(cid, TILT, "STARTED", progress=0, angle_deg=start,
                           message=f"Tilt requested {start:.0f} -> {target:.0f} deg (simulated servo)")
            direction = 1 if target >= start else -1
            angle = start
            while abs(target - angle) > 1e-9:
                await asyncio.sleep(cfg.tilt_step_s)
                angle += direction * min(cfg.tilt_step_deg, abs(target - angle))
                self.world.tilt_angle_deg = angle
                span = abs(target - start) or 1.0
                done = abs(angle - start) / span
                if abs(target - angle) > 1e-9:
                    self._feedback(cid, TILT, "IN_PROGRESS", progress=round(100 * done), angle_deg=angle)
            self.world.tilt_active = False
            self.world.finish_tilt()
            self._feedback(cid, TILT, "COMPLETED", progress=100, angle_deg=angle,
                           message=f"Tilt reached {angle:.0f} deg (simulated)")
        finally:
            self.world.tilt_active = False
            self.busy = False

    def _feedback(self, command_id, actuator, state, progress=None, angle_deg=None, message=""):
        seq, sim_time = self._sim_time()
        self.bus.publish(TOPIC_FEEDBACK, envelope("feedback", seq, sim_time, {
            "command_id": command_id, "actuator": actuator, "state": state,
            "progress": progress, "angle_deg": angle_deg, "message": message,
            "source": "software_actuator_simulator",
        }))
