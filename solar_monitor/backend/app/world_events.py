"""Operator-triggered actions and what-if events ("suggested options" in the UI).

Everything here changes the SIMULATED world (the virtual panel and its surroundings); the pipeline only ever
sees the resulting sensor readings. Effects are simulation assumptions, not measurements:

  corrective actions  : clean (cleaning robot), rotate/tilt to an angle, return to flat   -> actuator command
  weather             : dust storm (deposits dust), rain (washes dust, dims light), passing cloud, heat wave
  time of day         : sunrise / noon / dusk / night  (sets the irradiance)
  faults & conditions : obstruction shadow on/off, hotspot (cell fault) on/off

Timed events run as asyncio tasks, restore their temporary modifiers when they end (or are cancelled) and
stream the world state so the 3D view follows in real time.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass, field

CAT_ACTIONS = "Corrective actions"
CAT_WEATHER = "Weather & environment"
CAT_TIME = "Time of day"
CAT_FAULTS = "Faults & conditions"


@dataclass
class EventDef:
    id: str
    label: str
    category: str
    icon: str
    description: str       # what the option does
    effect: str            # what you should see / how the pipeline reacts
    kind: str              # "actuator" | "timed" | "instant"
    duration_s: float = 0.0
    params: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _p(key, label, lo, hi, step, default, unit=""):
    return {"key": key, "label": label, "min": lo, "max": hi, "step": step, "default": default, "unit": unit}


CATALOG: list[EventDef] = [
    EventDef("clean", "Clean panel", CAT_ACTIONS, "broom",
             "Send the cleaning robot across the glass.",
             "Dust disappears behind the brush; verification checks the recovery.", "actuator"),
    EventDef("tilt", "Rotate panel", CAT_ACTIONS, "tilt",
             "Rotate the panel to a chosen servo angle (90° = flat, above 90° leans toward the sun).",
             "Shadow shrinks when leaning toward the sun and grows when leaning away (simulation assumption).", "actuator",
             params=[_p("angle", "Servo angle", 30, 150, 5, 120, "°")]),
    EventDef("flat", "Return to flat (90°)", CAT_ACTIONS, "flat",
             "Rotate the panel back to the default horizontal position.", "Undoes any tilt.", "actuator"),

    EventDef("dust_storm", "Dust storm", CAT_WEATHER, "dust",
             "Wind-blown dust settles on the glass for a few seconds.",
             "Dust builds up; power deviation rises; classification turns to soiling.", "timed", 6),
    EventDef("rain", "Rain shower", CAT_WEATHER, "rain",
             "A short rain shower washes part of the dust off.",
             "Dust fades while light drops; a natural clean without the robot.", "timed", 8),
    EventDef("cloud", "Passing cloud", CAT_WEATHER, "cloud",
             "A cloud passes in front of the sun.",
             "Power AND expected power fall together, so it is not flagged as a fault.", "timed", 8),
    EventDef("heat_wave", "Heat wave", CAT_WEATHER, "heat",
             "Ambient temperature rises by 12 °C for a while.",
             "Thermal grid warms up, expected power falls slightly; no hotspot by itself.", "timed", 15),

    EventDef("sunrise", "Sunrise", CAT_TIME, "sunrise", "Low morning sun (250 W/m²).", "Dim light, low power.", "instant"),
    EventDef("noon", "Midday", CAT_TIME, "sun", "Strong midday sun (1000 W/m²).", "Full power.", "instant"),
    EventDef("dusk", "Dusk", CAT_TIME, "dusk", "Fading evening light (120 W/m²).", "Very low power; deviation stays meaningful.", "instant"),
    EventDef("night", "Night", CAT_TIME, "moon", "No sunlight (0 W/m²).", "Zero power; expected power is 0 so deviation is undefined (n/a).", "instant"),

    EventDef("shadow_on", "Add obstruction shadow", CAT_FAULTS, "shadow",
             "A nearby object shades 30 % more of the panel.",
             "Cool region on the thermal grid; classification turns to partial shading.", "instant"),
    EventDef("shadow_off", "Remove obstruction", CAT_FAULTS, "shadow_off", "Clear all shading.", "Shadow disappears.", "instant"),
    EventDef("hotspot_on", "Inject hotspot (cell fault)", CAT_FAULTS, "flame",
             "A faulty cell cluster overheats.",
             "Hotspot alert; the underlying class is preserved.", "instant",
             params=[_p("peak", "Peak temperature", 55, 110, 5, 75, "°C")]),
    EventDef("hotspot_off", "Repair hotspot", CAT_FAULTS, "wrench", "Remove the hotspot.", "Alert clears.", "instant"),
]
BY_ID = {e.id: e for e in CATALOG}
TIME_OF_DAY = {"sunrise": 250.0, "noon": 1000.0, "dusk": 120.0, "night": 0.0}


class EventRunner:
    def __init__(self, engine):
        self.engine = engine
        self._tasks: dict[str, asyncio.Task] = {}
        self._ends: dict[str, float] = {}

    # -- public --------------------------------------------------------------------------------------
    def catalog(self) -> list[dict]:
        return [e.to_dict() for e in CATALOG]

    def effects(self) -> list[dict]:
        now = time.monotonic()
        return [{"id": k, "label": BY_ID[k].label, "remaining_s": round(max(0.0, end - now), 1)} for k, end in self._ends.items()]

    def cancel(self, event_id: str) -> None:
        task = self._tasks.pop(event_id, None)
        if task:
            task.cancel()
        self._ends.pop(event_id, None)
        self._restore(event_id)
        self.engine._broadcast_truth()

    def cancel_all(self) -> None:
        for event_id in list(self._tasks):
            task = self._tasks.pop(event_id)
            task.cancel()
            self._restore(event_id)
        self._ends.clear()

    def run(self, event_id: str, params: dict | None = None) -> str:
        """Start an event. Returns a short human message. Raises ValueError for bad input/unknown events and
        RuntimeError when the actuator is busy."""
        ev = BY_ID.get(event_id)
        if ev is None:
            raise ValueError(f"Unknown event '{event_id}'")
        params = params or {}
        e = self.engine
        msg = f"{ev.label}"

        if ev.kind == "actuator":
            if event_id == "clean":
                ok, info = e.send_command("START_CLEANING", "operator", "Operator: clean panel")
            else:
                angle = 90.0 if event_id == "flat" else self._num(params, "angle", ev)
                ok, info = e.send_command("TILT_PANEL", "operator", f"Operator: rotate panel to {angle:.0f} deg", target_angle=angle)
                msg = f"{ev.label} to {angle:.0f}°"
            if not ok:
                raise RuntimeError(info)
        elif ev.kind == "timed":
            self._start_timed(event_id)
        else:
            self._instant(event_id, params)
        e._event("EVENT", f"Operator triggered: {msg} (simulated what-if).", "info", "runtime")
        return msg

    # -- helpers ----------------------------------------------------------------------------------------
    @staticmethod
    def _num(params: dict, key: str, ev: EventDef) -> float:
        spec = next(p for p in ev.params if p["key"] == key)
        try:
            v = float(params.get(key, spec["default"]))
        except (TypeError, ValueError):
            raise ValueError(f"{key}: not a number")
        if not (spec["min"] <= v <= spec["max"]):
            raise ValueError(f"{key}: {v} outside [{spec['min']}, {spec['max']}]")
        return v

    def _instant(self, event_id: str, params: dict) -> None:
        e = self.engine
        w = e.world
        if event_id in TIME_OF_DAY:
            e.update_params({"irradiance_Wm2": TIME_OF_DAY[event_id]})
        elif event_id == "shadow_on":
            e.update_params({"shading_fraction": min(0.9, w.params.shading_fraction + 0.3)})
        elif event_id == "shadow_off":
            e.update_params({"shading_fraction": 0.0})
        elif event_id == "hotspot_on":
            peak = self._num(params, "peak", BY_ID["hotspot_on"])
            e.update_params({"hotspot_enabled": True, "hotspot_peak_C": peak, "hotspot_pixels": max(4, w.params.hotspot_pixels)})
        elif event_id == "hotspot_off":
            e.update_params({"hotspot_enabled": False})
        e._broadcast_truth()

    def _start_timed(self, event_id: str) -> None:
        old = self._tasks.pop(event_id, None)
        if old:
            old.cancel()
        w = self.engine.world
        dur = max(0.02, BY_ID[event_id].duration_s * self.engine.config.event_time_scale)
        self._ends[event_id] = time.monotonic() + dur
        # the state change is visible immediately; the task only evolves it over time and unwinds it at the end
        w.weather[event_id] = True
        if event_id == "cloud":
            w.irr_mods["cloud"] = 0.3
        elif event_id == "rain":
            w.irr_mods["rain"] = 0.35
        elif event_id == "heat_wave":
            w.temp_mods["heat_wave"] = 12.0
        self.engine._broadcast_truth()
        self._tasks[event_id] = asyncio.get_running_loop().create_task(self._run_timed(event_id, dur))

    def _restore(self, event_id: str) -> None:
        w = self.engine.world
        w.weather[event_id] = False
        w.irr_mods.pop(event_id, None)
        w.temp_mods.pop(event_id, None)

    async def _run_timed(self, event_id: str, dur: float) -> None:
        e, w = self.engine, self.engine.world
        steps = max(2, int(dur / 0.5))
        dt = dur / steps
        finished = False
        try:
            for _ in range(steps):
                await asyncio.sleep(dt)
                if event_id == "dust_storm":
                    w.add_dust(0.48 / steps)
                elif event_id == "rain":
                    w.apply_cleaning(1 - 0.29 ** (1 / steps))   # ~71 % of the dust washed off in total
                e._broadcast_truth()
            finished = True
        finally:
            if self._tasks.get(event_id) is asyncio.current_task():
                self._tasks.pop(event_id, None)
                self._ends.pop(event_id, None)
                self._restore(event_id)
                e._broadcast_truth()
                if finished:
                    e._event("EVENT", f"{BY_ID[event_id].label} ended.", "info", "runtime")
