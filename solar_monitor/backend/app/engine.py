"""Simulation engine: wires world -> bus -> pipeline -> decision -> actuator -> verification.

Message flow (every arrow is a bus message, i.e. MQTT when a broker is connected):

  world.read() --solar/panel/data--> pipeline --solar/panel/status--> (UI / other subscribers)
  decision START_CLEANING | TILT_PANEL --solar/panel/command--> actuator simulator
  actuator simulator --solar/panel/feedback--> engine (completion -> post-action verification)
"""
from __future__ import annotations

import asyncio
import datetime
import time
from collections import deque
from copy import copy
from pathlib import Path

from .actuators import CLEANING, SUPPORTED, TILT, ActuatorSimulator
from .bus import MessageBus, clean
from .config import SimConfig
from .ml.loader import load_classifier
from .mqtt_link import MqttLink
from .pipeline import Pipeline
from .scenarios import SCENARIOS, SimParams, validate_params
from .topics import (TOPIC_COMMAND, TOPIC_DATA, TOPIC_FEEDBACK, TOPIC_STATUS, envelope, utc_now)
from .world import PanelWorld
from .world_events import EventRunner

DEFAULT_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
ACTION_LABEL = {CLEANING: "Cleaning", TILT: "Tilting"}


class SimulationEngine:
    def __init__(self, config: SimConfig | None = None, models_dir: Path | None = None,
                 mqtt: MqttLink | None = None, classifier_pref: str | None = None):
        self.config = config or SimConfig()
        self.models_dir = Path(models_dir or DEFAULT_MODELS_DIR)
        self._classifier_pref = classifier_pref
        self.bus = MessageBus()
        self.bus.on_error = self._bus_error
        self.mqtt = mqtt
        self.bus.mqtt = mqtt

        self.classifier, self.classifier_info = load_classifier(self.models_dir, self.config, classifier_pref)
        self.scenario_id = "healthy"
        self.scenario_label = SCENARIOS["healthy"].name
        self.world = PanelWorld(self.config, copy(SCENARIOS["healthy"].params))
        self.pipeline = Pipeline(self.config, self.classifier)
        self.actuator = ActuatorSimulator(self.bus, self.world, self.config, self._seq_time)
        self.events_runner = EventRunner(self)

        self.playing = True
        self.tick_no = 0
        self.sim_start = datetime.datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
        self.history: deque = deque(maxlen=400)
        self.events: deque = deque(maxlen=500)
        self.messages: deque = deque(maxlen=60)
        self._event_id = 0
        self._cmd_id = 0
        self._queues: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self._wake: asyncio.Event | None = None  # created in start() (needs a running loop)
        self._reset_epoch()
        self.last_result: dict | None = None

        self.bus.subscribe(TOPIC_DATA, self._on_data)
        self.bus.subscribe(TOPIC_COMMAND, self.actuator.on_command)
        self.bus.subscribe(TOPIC_FEEDBACK, self._on_feedback)
        self.bus.tap(self._on_any_message)

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self.bus.attach_loop(loop)
        self._wake = asyncio.Event()
        self._event("SYSTEM", "Simulation engine started (all sensor data is simulated).", "info", "runtime")
        ci = self.classifier_info
        if ci["mode"] == "simulated":
            self._event("SYSTEM", f"Classifier: SIMULATED stand-in ({ci['fallback_reason']}).", "info", "runtime")
        elif ci["mode"] == "trained_model":
            self._event("SYSTEM", f"Classifier: trained model '{ci['name']}' loaded.", "info", "runtime")
        else:
            self._event("SYSTEM", f"Classifier unavailable: {ci.get('error')}", "error", "runtime")
        if self.mqtt is not None:
            self.mqtt.start(self.bus.on_mqtt_message,
                            lambda st: loop.call_soon_threadsafe(self._on_mqtt_status, st))
        self._task = loop.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        self.actuator.cancel()
        self.events_runner.cancel_all()
        if self.mqtt is not None:
            self.mqtt.stop()

    async def _run(self) -> None:
        while True:
            if self.playing:
                self.tick()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.config.tick_interval_s)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    def _reset_epoch(self) -> None:
        """State tied to the current scenario (cleared on scenario change / reset)."""
        self.inflight: dict | None = None
        self.pending_verification: dict | None = None
        self.last_verification: dict | None = None
        self.failed_actions: set[str] = set()
        self._suppressed_logged: set[str] = set()
        self.action_state = {"phase": "idle", "action": None, "progress": 0, "angle_deg": None,
                             "command_id": None, "source": None, "message": ""}
        self.prev = {"class": None, "hotspot": None, "action": None, "secondary": None}
        self._epoch_tick = self.tick_no + 1  # first tick of the current physical situation ("before" baseline)

    def _truth(self) -> dict:
        t = self.world.truth()
        t["effects"] = self.events_runner.effects()
        return t

    def _broadcast_truth(self) -> None:
        self._broadcast({"type": "truth", "truth": self._truth()})

    # ------------------------------------------------------------------ time helpers
    def sim_time(self, tick: int) -> str:
        return (self.sim_start + datetime.timedelta(minutes=tick * self.config.sim_minutes_per_tick)
                ).isoformat(timespec="seconds")

    def _seq_time(self) -> tuple[int, str]:
        return self.tick_no, self.sim_time(self.tick_no)

    # ------------------------------------------------------------------ events / broadcast
    def _event(self, etype: str, message: str, level: str = "info", origin: str = "simulated") -> None:
        self._event_id += 1
        ev = {"id": self._event_id, "tick": self.tick_no, "sim_time": self.sim_time(self.tick_no),
              "wall_time": utc_now(), "type": etype, "level": level, "message": message,
              "origin": origin}  # origin: 'simulated' (derived from simulated data) | 'runtime' (software/operator)
        self.events.append(ev)
        self._broadcast({"type": "event", "event": ev})

    def _broadcast(self, msg: dict) -> None:
        msg = clean(msg)
        for q in list(self._queues):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    def register_client(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._queues.add(q)
        return q

    def unregister_client(self, q: asyncio.Queue) -> None:
        self._queues.discard(q)

    def _bus_error(self, topic: str, exc: Exception) -> None:
        self._event("ERROR", f"Message on {topic} could not be processed: {type(exc).__name__}: {exc}", "error", "runtime")

    def _on_any_message(self, topic: str, data: dict, transport: str) -> None:
        rec = {"topic": topic, "transport": transport, "payload": data, "wall_time": utc_now(),
               "sim_time": data.get("sim_time")}
        self.messages.append(clean(rec))
        self._broadcast({"type": "bus", "message": rec})

    def _on_mqtt_status(self, status: dict) -> None:
        if status["connected"]:
            self._event("MQTT", f"Connected to MQTT broker {status['host']}:{status['port']} - messages now travel through the broker.", "success", "runtime")
        else:
            self._event("MQTT", f"MQTT broker not connected ({status.get('last_error')}) - local simulation mode.", "warn", "runtime")
        self._broadcast({"type": "mqtt", "mqtt": self.mqtt_status()})

    def mqtt_status(self) -> dict:
        if self.mqtt is None:
            return {"enabled": False, "connected": False, "host": None, "port": None,
                    "mode": "local_simulation", "last_error": "MQTT client not configured"}
        return self.mqtt.status()

    # ------------------------------------------------------------------ the simulation tick
    def tick(self) -> None:
        self.tick_no += 1
        self._check_command_timeout()
        telemetry = self.world.read()
        self.bus.publish(TOPIC_DATA, envelope("telemetry", self.tick_no, self.sim_time(self.tick_no), telemetry))

    def _on_data(self, msg: dict) -> None:
        try:
            r = self.pipeline.process(msg)
        except ValueError as e:
            self._event("ERROR", str(e), "error", "runtime")
            return
        seq = int(msg.get("seq", self.tick_no))
        sim_time = msg.get("sim_time") or self.sim_time(seq)
        r["tick"], r["sim_time"] = seq, sim_time
        self.last_result = r
        tw, dec, th, ml = r["twin"], r["decision"], r["thermal"], r["ml"]

        point = {
            "tick": seq, "sim_time": sim_time[11:16], "power": tw["power_actual_W"],
            "expected": tw["power_expected_W"], "deviation": tw["deviation_pct"], "health": tw["health_score_pct"],
            "t_max": th["max_temp_C"], "t_avg": th["mean_temp_C"], "tilt": tw["tilt_angle_deg"],
            "hotspot": th["hotspot_detected"] == "YES", "ml_class": dec["ml_class"], "action": dec["recommended_action"],
        }
        self.history.append(point)

        self._detect_events(r)
        self._collect_verification(msg, point)

        # publish the combined state (ML class and hotspot kept separate and preserved)
        self.bus.publish(TOPIC_STATUS, envelope("status", seq, sim_time, self._status_body(r)))

        # auto-execute corrective actions (a hotspot alert does NOT withhold the underlying cleaning / tilt)
        if self.config.auto_execute and not (self.inflight or self.pending_verification):
            cmd, suppressed = self._pick_command(r)
            if cmd:
                self.send_command(cmd, "decision_engine", dec["reason"])
            elif suppressed and suppressed not in self._suppressed_logged:
                self._suppressed_logged.add(suppressed)
                self._event("DECISION", f"{ACTION_LABEL[suppressed]} auto-retry suppressed after failed verification - operator inspection required.", "warn")

        self._broadcast({"type": "tick", "result": self._ui_result(r), "history_point": point,
                         "truth": self._truth(), "sim": self.sim_state()})

    def _pick_command(self, r: dict) -> tuple[str | None, str | None]:
        """Next actuator command the decision engine wants: (command, suppressed_command).

        Walks the engine's ordered `auto_actions` (e.g. tilt, then clean for combined shading + soiling).
        Commands whose previous verification failed are suppressed; a tilt is skipped once the servo is
        already at the target angle. Duplicates are prevented by the in-flight / pending-verification guard
        and because the condition (and thus the recommendation) disappears once the action has worked.
        """
        suppressed = None
        for action in r["decision"].get("auto_actions", []):
            cmd = SUPPORTED_DECISIONS[action]
            if cmd in self.failed_actions:
                suppressed = suppressed or cmd
            elif cmd == TILT and self.world.tilt_angle_deg >= self.config.tilt_target_angle_deg - 1e-6:
                continue   # servo already at its limit: another tilt cannot recover anything
            else:
                return cmd, None
        return None, suppressed

    def _status_body(self, r: dict) -> dict:
        tw, dec, th, ml = r["twin"], r["decision"], r["thermal"], r["ml"]
        return {
            "voltage_V": tw["voltage_V"], "current_A": tw["current_A"], "power_actual_W": tw["power_actual_W"],
            "power_expected_W": tw["power_expected_W"], "performance_deviation_pct": tw["deviation_pct"],
            "health_score_pct": tw["health_score_pct"], "energy_loss_Wh_est": tw["energy_loss_Wh_est"],
            "lux": tw["lux"], "temperature_C": tw["temperature_C"], "irradiance_Wm2": tw["irradiance_Wm2"],
            "irradiance_source": tw["irradiance_source"],
            "ml_class": dec["ml_class"], "ml_confidence": ml["confidence"], "classifier_mode": ml["mode"],
            "ml_error": ml["error"],
            "hotspot": th["hotspot_detected"], "hotspot_row": th["hotspot_row"], "hotspot_col": th["hotspot_col"],
            "max_temp_C": th["max_temp_C"], "mean_temp_C": th["mean_temp_C"], "hot_pixel_count": th["hot_pixel_count"],
            "persistent_degrad": tw["persistent_degrad"], "persist_count": tw["persist_count"],
            "final_status": dec["final_status"], "recommended_action": dec["recommended_action"],
            "underlying_action": dec["base_action"], "reason": dec["reason"],
            "secondary_condition": dec.get("secondary_condition"), "health": tw.get("health"),
            "tilt_angle_deg": tw["tilt_angle_deg"], "cleaning_active": tw["cleaning_state"],
        }

    # ------------------------------------------------------------------ events from data
    def _detect_events(self, r: dict) -> None:
        dec, th = r["decision"], r["thermal"]
        cls, hs, act = dec["ml_class"], th["hotspot_detected"], dec["recommended_action"]
        p = self.prev
        if cls != p["class"]:
            msg = f"Condition classified: {cls}" if p["class"] is None else f"Condition changed: {p['class']} -> {cls}"
            self._event("CONDITION", msg, "warn" if cls != "Healthy_Clean" else "info")
        if hs != p["hotspot"]:
            if hs == "YES":
                self._event("HOTSPOT", f"HOTSPOT ALERT: max {th['max_temp_C']:.1f} C at pixel ({th['hotspot_row']},{th['hotspot_col']}), "
                            f"{th['hot_pixel_count']} hot px. Underlying condition preserved: {cls}.", "alert")
            elif p["hotspot"] == "YES":
                self._event("HOTSPOT", "Hotspot cleared.", "success")
        if act != p["action"] and act not in ("NO_ACTION",):
            if act == "START_CLEANING":
                self._event("DECISION", f"Decision: START_CLEANING - {dec['reason']}", "warn")
            elif act == "TILT_PANEL":
                self._event("DECISION", f"Decision: TILT_PANEL - {dec['reason']}", "warn")
            elif act == "WAIT":
                self._event("DECISION", f"Decision: WAIT - {dec['reason']}", "info")
            elif act.startswith("HOTSPOT"):
                self._event("DECISION", f"Decision: {act} (underlying action: {dec['base_action']}).", "alert")
            else:
                self._event("DECISION", f"Decision: {act} - {dec['reason']}", "warn")
        sec = dec.get("secondary_condition")
        if sec != p.get("secondary") and sec:
            self._event("CONDITION", "Combined condition: partial shading (ML class) with concurrent soiling inferred from the power "
                        "shortfall. Tilt first, then clean. The ML class is unchanged.", "warn")
        p["class"], p["hotspot"], p["action"], p["secondary"] = cls, hs, act, sec

    # ------------------------------------------------------------------ commands / feedback
    def send_command(self, action: str, source: str, reason: str = "",
                     target_angle: float | None = None) -> tuple[bool, str]:
        if action not in SUPPORTED:
            return False, f"Unsupported command '{action}'"
        if self.inflight:
            return False, "An action is already in progress"
        if self.pending_verification:
            if source != "operator":
                return False, "The previous action is still awaiting verification"
            self.pending_verification = None   # a new operator command supersedes the pending check
            self._event("VERIFY", "Pending verification abandoned - a new operator command supersedes it.", "info", "runtime")
        if source == "operator":
            self.failed_actions.discard(action)
        self._cmd_id += 1
        cid = f"cmd-{self._cmd_id}"
        pre = self._pre_snapshot()
        pre["combined"] = bool(self.last_result and self.last_result["decision"].get("secondary_condition"))
        self.inflight = {"command_id": cid, "action": action, "t0": time.monotonic(), "pre": pre, "source": source}
        self.action_state = {"phase": "commanded", "action": action, "progress": 0, "angle_deg": self.world.tilt_angle_deg,
                             "command_id": cid, "source": source, "message": "Command published"}
        body = {"command": action, "command_id": cid, "source": source, "reason": reason}
        if action == TILT:
            body["target_angle_deg"] = float(target_angle) if target_angle is not None else self.config.tilt_target_angle_deg
        self.bus.publish(TOPIC_COMMAND, envelope("command", self.tick_no, self.sim_time(self.tick_no), body))
        who = "decision engine" if source == "decision_engine" else "operator (manual)"
        self._event("COMMAND", f"{ACTION_LABEL[action]} command sent by {who} on {TOPIC_COMMAND}.",
                    "warn", "simulated" if source == "decision_engine" else "runtime")
        self._broadcast_action()
        return True, cid

    def _pre_snapshot(self) -> dict:
        pts = [p for p in self.history if p["tick"] >= self._epoch_tick][-3:]
        if not pts:
            return {"power": None, "expected": None, "deviation": None, "health": None, "n": 0}
        mean = lambda k: round(sum(p[k] for p in pts if p[k] is not None) / max(1, len([p for p in pts if p[k] is not None])), 3)  # noqa: E731
        return {"power": mean("power"), "expected": mean("expected"), "deviation": mean("deviation"),
                "health": mean("health"), "n": len(pts)}

    def _on_feedback(self, msg: dict) -> None:
        state, action, cid = msg.get("state"), msg.get("actuator"), msg.get("command_id")
        a = self.action_state
        a.update({"action": action, "command_id": cid, "message": msg.get("message", ""),
                  "progress": msg.get("progress") if msg.get("progress") is not None else a.get("progress", 0)})
        if msg.get("angle_deg") is not None:
            a["angle_deg"] = msg["angle_deg"]
        if state == "STARTED":
            a["phase"] = "running"
            self._event("ACTION", f"{ACTION_LABEL.get(action, action)} started (simulated actuator).", "info")
        elif state == "IN_PROGRESS":
            a["phase"] = "running"
        elif state == "COMPLETED":
            a["phase"] = "completed"
            pre = (self.inflight or {}).get("pre") or self._pre_snapshot()
            self.pending_verification = {"action": action, "pre": pre, "readings": [], "min_revision": self.world.revision,
                                         "command_id": cid}
            self.inflight = None
            self._event("ACTION", f"{ACTION_LABEL.get(action, action)} completed - verifying with next "
                        f"{self.config.verification_cycles} readings.", "success")
        elif state == "REJECTED":
            a["phase"] = "rejected"
            self.inflight = None
            self._event("ACTION", f"{ACTION_LABEL.get(action, action)} command rejected: {msg.get('message')}", "error")
        # keep live views (3D scene) in step with the world: tilt angle, dust and shade change during actions
        self._broadcast_truth()
        self._broadcast_action()

    def _check_command_timeout(self) -> None:
        if self.inflight and time.monotonic() - self.inflight["t0"] > self.config.command_timeout_s:
            act = self.inflight["action"]
            self._event("ACTION", f"No feedback for {ACTION_LABEL[act]} command within {self.config.command_timeout_s:.0f}s - abandoned.", "error", "runtime")
            self.action_state.update({"phase": "timeout", "message": "No feedback received"})
            self.inflight = None
            self._broadcast_action()

    # ------------------------------------------------------------------ verification
    def _collect_verification(self, msg: dict, point: dict) -> None:
        pv = self.pending_verification
        if not pv or msg.get("world_revision", 0) < pv["min_revision"]:
            return
        pv["readings"].append(point)
        if len(pv["readings"]) < self.config.verification_cycles:
            self._broadcast_stages()
            return
        rs = pv["readings"]
        avg = lambda k: sum(x[k] for x in rs if x[k] is not None) / max(1, len([x for x in rs if x[k] is not None]))  # noqa: E731
        post = {"power": round(avg("power"), 3), "expected": round(avg("expected"), 3),
                "deviation": round(avg("deviation"), 2) if any(x["deviation"] is not None for x in rs) else None,
                "health": round(avg("health"), 2) if any(x["health"] is not None for x in rs) else None}
        pre, thr = pv["pre"], self.config.verification_dev_thresh_pct
        combined_tilt = pv["action"] == TILT and pre.get("combined")
        gain_pct_now = None if not pre.get("power") else 100 * (post["power"] - pre["power"]) / pre["power"]
        if post["deviation"] is None:
            verdict = "INCONCLUSIVE"
        elif combined_tilt and gain_pct_now is not None and gain_pct_now >= thr:
            verdict = "RECOVERED"      # shading part recovered; the residual (soiling) is handled by the queued cleaning
        elif abs(post["deviation"]) >= thr:
            verdict = "NOT_RECOVERED"
        elif pre.get("deviation") is not None and abs(pre["deviation"]) < thr:
            verdict = "NO_CHANGE"      # performance was already within limits: nothing to recover
        else:
            verdict = "RECOVERED"
        gain = None if pre.get("power") is None else round(post["power"] - pre["power"], 3)
        gain_pct = None if not pre.get("power") else round(100 * (post["power"] - pre["power"]) / pre["power"], 1)
        self.last_verification = {
            "action": pv["action"], "verdict": verdict, "pre": pre, "post": post, "power_gain_W": gain,
            "power_gain_pct": gain_pct, "readings": len(rs),
            "criterion": f"mean |deviation| of {len(rs)} post-action readings < {thr}%",
            "simulation_note": ("Recovery is SIMULATED from explicit model assumptions "
                                "(cleaning effectiveness / tilt efficacy in config); it is not a physical experiment."),
        }
        self.pending_verification = None
        self._epoch_tick = self.tick_no + 1
        if verdict == "NO_CHANGE":
            self.failed_actions.discard(pv["action"])
            self._event("VERIFY", f"{ACTION_LABEL[pv['action']]} verification: performance was already within limits "
                        f"(deviation {pre.get('deviation')}% -> {post['deviation']}%) - no recovery to confirm.", "info")
        elif verdict == "RECOVERED" and combined_tilt and abs(post["deviation"]) >= thr:
            self.failed_actions.discard(pv["action"])
            self._event("VERIFY", f"Tilt verification: shading component recovered (power {pre.get('power')} W -> {post['power']} W, "
                        f"deviation {pre.get('deviation')}% -> {post['deviation']}%); residual shortfall attributed to soiling - cleaning follows. Simulated.", "success")
        elif verdict == "RECOVERED":
            self.failed_actions.discard(pv["action"])
            self._event("VERIFY", f"{ACTION_LABEL[pv['action']]} verification PASSED: deviation {pre.get('deviation')}% -> {post['deviation']}% "
                        f"(power {pre.get('power')} W -> {post['power']} W). Simulated recovery.", "success")
        else:
            self.failed_actions.add(pv["action"])
            self._event("VERIFY", f"{ACTION_LABEL[pv['action']]} verification {'FAILED' if verdict == 'NOT_RECOVERED' else 'INCONCLUSIVE'}: "
                        f"post-action deviation {post['deviation']}% (needs < {thr}%). Not claiming success.", "error")
        self._broadcast({"type": "verification", "verification": self.last_verification})
        self._broadcast_stages()

    # ------------------------------------------------------------------ stages (7 & 8)
    def stages(self) -> list[dict]:
        r = self.last_result
        if not r:
            return []
        base = [dict(s) for s in r["stages"]]
        d, a, cfg = r["decision"], self.action_state, self.config
        act = d["recommended_action"]
        label = ACTION_LABEL.get(a.get("action"), "Action")
        if a["phase"] in ("commanded", "running"):
            ang = f", {a['angle_deg']:.0f} deg" if a.get("action") == TILT and a.get("angle_deg") is not None else ""
            s7 = {"state": "active", "headline": f"{label} in progress {a.get('progress') or 0}%{ang}",
                  "details": {"Command": a.get("command_id"), "Source": a.get("source"), "Note": "SIMULATED actuator"}}
        elif a["phase"] == "completed":
            s7 = {"state": "done", "headline": f"{label} completed (simulated)", "details": {"Command": a.get("command_id"), "Note": a.get("message")}}
        elif a["phase"] in ("rejected", "timeout"):
            s7 = {"state": "error", "headline": f"{label} {a['phase']}", "details": {"Note": a.get("message")}}
        elif act == "NO_ACTION":
            s7 = {"state": "done", "headline": "No intervention", "details": {}}
        elif act == "WAIT":
            s7 = {"state": "pending", "headline": "Waiting for persistence",
                  "details": {"Persistence": f"{r['twin']['persist_count']}/{cfg.persist_cycles}"}}
        elif d.get("auto_actions"):
            cmd, suppressed = self._pick_command(r)
            if cmd is None and suppressed:
                s7 = {"state": "error", "headline": "Auto-retry suppressed", "details": {"Reason": "previous verification failed"}}
            else:
                s7 = {"state": "pending", "headline": "Awaiting command" if cfg.auto_execute else "Awaiting operator",
                      "details": {"Auto-execute": "on" if cfg.auto_execute else "off",
                                  **({"Hotspot": "alert raised; repair is a separate manual action"} if act.startswith("HOTSPOT") else {})}}
        elif act.startswith("HOTSPOT"):
            s7 = {"state": "alert", "headline": "Hotspot alert raised", "details": {"Underlying": d["base_action"], "Auto-action": "none (alert only)"}}
        else:
            s7 = {"state": "error", "headline": act, "details": {}}
        s7.update(id="action", title="Corrective action")

        v, pv = self.last_verification, self.pending_verification
        if pv:
            s8 = {"state": "active", "headline": f"Collecting {len(pv['readings'])}/{cfg.verification_cycles} readings", "details": {}}
        elif v:
            ok = v["verdict"] == "RECOVERED"
            s8 = {"state": "done" if ok else "error", "headline": v["verdict"].replace("_", " "),
                  "details": {"Deviation": f"{v['pre'].get('deviation')}% -> {v['post']['deviation']}%", "Criterion": v["criterion"]}}
        else:
            s8 = {"state": "pending", "headline": "No action to verify", "details": {}}
        s8.update(id="verification", title="Post-action verification")
        return base + [s7, s8]

    def _broadcast_stages(self) -> None:
        self._broadcast({"type": "stages", "stages": self.stages()})

    def _broadcast_action(self) -> None:
        self._broadcast({"type": "action", "action": self.action_state})
        self._broadcast_stages()

    def _ui_result(self, r: dict) -> dict:
        out = dict(r)
        out["stages"] = self.stages()
        return out

    # ------------------------------------------------------------------ operator API
    def sim_state(self) -> dict:
        return {"playing": self.playing, "tick": self.tick_no, "sim_time": self.sim_time(self.tick_no),
                "tick_interval_s": self.config.tick_interval_s}

    def select_scenario(self, scenario_id: str) -> None:
        sc = SCENARIOS.get(scenario_id)
        if sc is None:
            raise ValueError(f"Unknown scenario '{scenario_id}'")
        self.actuator.cancel()
        self.events_runner.cancel_all()
        self.scenario_id, self.scenario_label = sc.id, sc.name
        self.world.reset(copy(sc.params))
        self.pipeline.reset()
        self._reset_epoch()
        self._event("SCENARIO", f"Scenario selected: {sc.name}. Expected: {sc.expected}", "info", "runtime")
        self._broadcast({"type": "scenario", "scenario_id": self.scenario_id, "scenario_label": self.scenario_label,
                         "params": self.world.params.to_dict(), "truth": self._truth()})
        self._broadcast_action()
        self._broadcast({"type": "verification", "verification": None})
        self.tick()

    def update_params(self, changes: dict) -> None:
        valid = validate_params(changes)
        self.world.set_params(valid)
        self._epoch_tick = self.tick_no + 1
        self.failed_actions.clear()
        self._suppressed_logged.clear()
        if not self.scenario_label.endswith("(modified)"):
            self.scenario_label = f"{SCENARIOS[self.scenario_id].name} (modified)"
        self._event("PARAMS", "Simulation parameters changed: " + ", ".join(f"{k}={v}" for k, v in valid.items()), "info", "runtime")
        self._broadcast({"type": "scenario", "scenario_id": self.scenario_id, "scenario_label": self.scenario_label,
                         "params": self.world.params.to_dict(), "truth": self._truth()})

    def update_config(self, changes: dict) -> None:
        changed = self.config.update(changes)
        if changed:
            self.failed_actions.clear()
            self._suppressed_logged.clear()
            self._event("CONFIG", "Configuration changed: " + ", ".join(f"{k}={getattr(self.config, k)}" for k in changed), "info", "runtime")
            if "seed" in changed:
                self.world.reset()
            self._broadcast({"type": "config", "config": self.config.to_dict()})
            if "tick_interval_s" in changed and self._wake is not None:
                self._wake.set()

    def set_playing(self, playing: bool) -> None:
        self.playing = playing
        self._event("SIM", "Simulation resumed." if playing else "Simulation paused.", "info", "runtime")
        self._broadcast({"type": "sim", "sim": self.sim_state()})
        if playing and self._wake is not None:
            self._wake.set()

    def step(self) -> None:
        self.tick()
        self._broadcast({"type": "sim", "sim": self.sim_state()})

    def reset(self) -> None:
        self.actuator.cancel()
        self.events_runner.cancel_all()
        sc = SCENARIOS[self.scenario_id]
        self.world.reset(copy(sc.params))
        self.pipeline.reset()
        self.history.clear()
        self.events.clear()
        self.messages.clear()
        self.tick_no = 0
        self._reset_epoch()
        self.last_result = None
        self.scenario_label = sc.name
        self._event("SIM", "Simulation reset (clock, history and events cleared).", "info", "runtime")
        self._broadcast(self.snapshot())
        self.tick()

    def run_event(self, event_id: str, params: dict | None = None) -> str:
        return self.events_runner.run(event_id, params)

    def reload_classifier(self) -> dict:
        self.classifier, self.classifier_info = load_classifier(self.models_dir, self.config, self._classifier_pref)
        self.pipeline.set_classifier(self.classifier)
        self._event("SYSTEM", f"Classifier reloaded: mode={self.classifier_info['mode']}.", "info", "runtime")
        self._broadcast({"type": "classifier", "classifier": self.classifier_info})
        return self.classifier_info

    async def wait_idle(self, timeout: float = 15.0) -> None:
        """Test helper: wait until queued messages are delivered and no command is in flight
        (post-action verification additionally needs further ticks)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            await asyncio.sleep(0)
            if self.bus.pending == 0 and not self.inflight and not self.actuator.busy:
                await asyncio.sleep(0)
                if self.bus.pending == 0:
                    return
            await asyncio.sleep(0.005)
        raise TimeoutError("engine did not become idle")

    def snapshot(self) -> dict:
        return clean({
            "type": "snapshot",
            "scenarios": [{"id": s.id, "name": s.name, "description": s.description, "expected": s.expected,
                           "params": s.params.to_dict()} for s in SCENARIOS.values()],
            "scenario_id": self.scenario_id, "scenario_label": self.scenario_label,
            "params": self.world.params.to_dict(), "truth": self._truth(),
            "config": self.config.to_dict(), "sim": self.sim_state(),
            "result": self._ui_result(self.last_result) if self.last_result else None,
            "history": list(self.history), "events": list(self.events), "messages": list(self.messages),
            "action": self.action_state, "verification": self.last_verification,
            "classifier": self.classifier_info, "mqtt": self.mqtt_status(),
            "event_catalog": self.events_runner.catalog(),
        })


SUPPORTED_DECISIONS = {"START_CLEANING": CLEANING, "TILT_PANEL": TILT}
