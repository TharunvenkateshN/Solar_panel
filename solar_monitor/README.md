# Solar Panel Monitoring - Software Simulation

Intelligent solar-panel monitoring, self-adaptive cleaning and predictive fault diagnosis (IoT + ML):
a complete, interactive, **software-only** demonstration that runs locally on Windows. No hardware,
no cloud, no public deployment. Every sensor reading is simulated and labelled as such.

```
Virtual sensors -> feature preparation -> ML classification -> hotspot detection
   -> expected-performance comparison -> decision engine -> corrective action -> post-action verification
```

## Quick start (Windows)

One-time setup (needs internet once for the packages):

```bash
setup.bat
```

Run (works offline afterwards):

```bash
start.bat
```

then open **http://localhost:8000**. (Equivalent: `python run.py`.)

Requirements: Python 3.10+, Node.js only to (re)build the frontend. A pre-built `frontend/dist` is included
after setup, so Node is not needed at runtime.

### Optional: real MQTT broker (Mosquitto)

Without a broker the app runs in an explicit **"MQTT: local simulation mode"** (messages are delivered
in-process and the UI says so). With Mosquitto running, the same messages really travel through the broker:

1. Install Mosquitto for Windows, then from `solar_monitor/mosquitto`:
   `"C:\Program Files\mosquitto\mosquitto.exe" -c mosquitto.conf -v`
2. Start the app. The header turns green: *MQTT broker 127.0.0.1:1883 - live*. If the broker is started
   later, the app connects automatically (auto-reconnect).
3. Watch the traffic in MQTT Explorer (subscribe to `solar/panel/#`), or in the dashboard's *MQTT message monitor*.

Env vars: `MQTT_HOST`, `MQTT_PORT`, `MQTT_ENABLED=0` (force local mode), `PORT` (web port), `SOLAR_CLASSIFIER=auto|simulated|model`.

## The dashboard

A light, accessible interface with a sidebar for navigation (hash routes, so pages can be bookmarked) and a top bar that is
always available: quick **scenario switch**, **Run / Pause / Step / Reset**, the simulation clock and honest status chips
(simulation, MQTT mode, classifier mode). While a cleaning or tilt action runs, a banner on every page offers **Watch in 3D**.

| Page | What it shows |
|---|---|
| Overview | Status banner, live 3D panel, pipeline rail, latest events, grouped live readings |
| Scenarios & controls | The 8 scenarios, sliders for irradiance / temperature / soiling / shade / hotspot, what the pipeline derived |
| 3D panel & actions | Large 3D rig, manual cleaning / tilt, before-vs-after power and verification verdict |
| Thermal & sensors | 8x8 thermal grid, hotspot rules, sensor readings, synthesised I-V curve, classifier features |
| Workflow | All 8 pipeline stages in detail and the decision-rule table (current row highlighted) |
| Analytics | Power, deviation / health and temperature trends with event markers |
| Events & MQTT | Filterable event history and the MQTT message monitor |
| Settings | Thresholds, simulated-actuator assumptions, classifier reload, MQTT status |
| About | Implemented vs simulated vs pending |

### 3D view (three.js)

The rig mirrors the simulator state in real time: **tilt angle** (servo 90 degrees = flat, +30 = leaning toward the sun) with a
tilt gauge, **dust** (procedural dust layer whose density follows the effective soiling), **shade** (soft shadow patch that
shrinks as the panel tilts), the **cleaning robot** sweeping the glass with spray and a wet sheen (dust is removed behind the
brush according to the configured cleaning effectiveness, so a weak cleaning visibly leaves dust), and an optional
**thermal overlay** (the 8x8 grid draped on the cells; hotspots glow in normal mode). Drag to orbit, scroll to zoom, or pick
Perspective / Side (angle) / Top. It visualises the simulation; it is not a physical measurement and needs WebGL.

### Actions and what-if events (suggested options)

The **3D panel & actions** page (and a compact "Try an action" card on the Overview) offers a **suggested** set of options for the
current situation plus every available option, grouped. Each one changes the *simulated* world and you watch it happen in the 3D view:

| Group | Options | What you see |
|---|---|---|
| Corrective actions | Clean panel · Rotate panel to a chosen angle (30-150°) · Return to flat | Brush sweep with spray and dust removal; panel turning on its pivot with the angle gauge |
| Weather & environment | Dust storm · Rain shower · Passing cloud · Heat wave | Blowing dust that settles on the glass · rain that washes it off · a cloud that dims the sun · warm light and a warmer thermal grid |
| Time of day | Sunrise · Midday · Dusk · Night | Sun intensity and sky follow the irradiance (night = 0 W/m², deviation is "n/a", never a fake number) |
| Faults & conditions | Add / remove obstruction shadow · Inject hotspot (peak temperature slider) / repair | Shadow patch on the glass · glowing hot cells |

The pipeline reacts only through the sensor readings: a cloud lowers measured **and** expected power together (not a fault), a dust
storm turns the class to soiling, a shadow to partial shading, a hotspot raises the alert while the class is preserved. Assumptions
(documented in `world.py` / `world_events.py`): rain washes ~71 % of the dust and dims light to 35 %, a cloud dims light to 30 %, a heat
wave adds 12 °C, a dust storm deposits 0.48 soiling. **Rotating toward the sun (angle > 90°) shrinks a shadow, rotating away enlarges it**;
there is no sun-tracking model, so tilting changes power only through the shadow. A rotate / clean on a panel that was already within limits
is reported as "already within limits - no recovery needed" rather than a fake recovery. `POST /api/event/{id}` triggers an option from any client.

## How to demonstrate it

1. Pick a scenario (left, or in the top bar). Watch the status banner, readings, thermal grid and the 8-stage workflow.
2. **Soiled / Dusty**: WAIT for 2 cycles -> `START_CLEANING` -> cleaning animation -> before/after power -> verification verdict.
3. **Partial shading**: `TILT_PANEL` immediately (never cleaning) -> tilt animation -> before/after -> verdict.
4. **Hotspot scenarios**: `HOTSPOT_ALERT[_WITH_...]` while the ML class stays visible. No automatic actuation.
5. **Custom** (or move any slider in another scenario): irradiance, background temperature, soiling, shaded area,
   hotspot on/off, peak temperature, area (pixels), position. These change the simulated sensor data; the class,
   hotspot result and action are *derived*, not looked up.
6. Make verification fail honestly: lower *Cleaning effectiveness* (Configuration panel) or *Tilt efficacy*, run a scenario.
   The verdict becomes **NOT recovered**, auto-retry is suppressed and an error event is logged.
7. Pause / Step / Run, and the manual cleaning/tilt buttons, let you narrate each cycle.

## Architecture

```
 PanelWorld (virtual INA219 / BH1750 / AMG8833 + actuator state)
      | solar/panel/data
      v
 Pipeline: features -> classifier adapter -> hotspot detector -> digital twin -> decision engine
      | solar/panel/status                      | START_CLEANING / TILT_PANEL
      v                                         v  solar/panel/command
 WebSocket -> React dashboard         ActuatorSimulator -> solar/panel/feedback -> verification
                  (all of it over MessageBus: Mosquitto when connected, in-process otherwise)
```

```
backend/app/
  core/            ported from the notebook: sensors.py, thermal.py, hotspot.py, digital_twin.py, decision_engine.py
  ml/              base.py (adapter contract), simulated.py, joblib_model.py, loader.py, features.py
  world.py         the virtual panel (physical model + actuator effects)
  scenarios.py     the 8 presets (physical parameters only)
  world_events.py  catalog + runner for the operator what-if events (weather, time of day, faults, rotate / clean)
  pipeline.py      one reading through the whole chain
  engine.py        wiring, persistence over time, auto-execution, verification, events
  bus.py, mqtt_link.py   message bus + real paho-mqtt client with auto-reconnect
  actuators.py     software cleaning / tilt simulator
  main.py          FastAPI REST + WebSocket + static frontend
backend/models/    drop-in folder for the trained model (see its README)
backend/tests/     129 tests
frontend/src/      React + Vite + Recharts + three.js dashboard (views/, widgets/, three/PanelScene.js)
```

The decision engine, hotspot detector, expected-power model and sensors exist **once**, in Python (ported from
`solar_panel_ai_completed.ipynb`, rules unchanged). The frontend only renders what the backend computed.

### MQTT topics and messages

All messages share one envelope: `schema_version`, `panel_id`, `type`, `is_simulated`, `seq`, `sim_time`, `timestamp`.

| Topic | Publisher | Body (besides the envelope) |
|---|---|---|
| `solar/panel/data` | virtual sensors | `ina219`, `bh1750`, `amg8833.grid` (8x8), `actuators` |
| `solar/panel/status` | pipeline | readings, `ml_class`, `ml_confidence`, `hotspot`, `final_status`, `recommended_action`, `underlying_action`, deviation, health ... |
| `solar/panel/command` | decision engine / operator | `command` (`START_CLEANING` \| `TILT_PANEL`), `command_id`, `source`, `target_angle_deg` |
| `solar/panel/feedback` | actuator simulator (or future hardware) | `command_id`, `actuator`, `state` (`STARTED` \| `IN_PROGRESS` \| `COMPLETED` \| `REJECTED`), `progress`, `angle_deg` |

Any other MQTT client can publish telemetry to `solar/panel/data` (it is processed like simulated data) or answer
commands on `solar/panel/feedback` (set *Built-in actuator simulator* off first).

## Plugging in the trained model later

Copy `solar_panel_condition_model.joblib` (+ `model_metadata.json`, `feature_schema.json`) into `backend/models/`
and press *Reload model* (or restart). No code changes. Details and failure behaviour: `backend/models/README.md`.

Until then a **simulated classifier** runs: a transparent rule set (cool thermal region -> `Partial_Shading`;
power shortfall without a cool region -> `Soiling_Dusty`; otherwise `Healthy_Clean`) computed from the generated
data. It is clearly labelled in the header, in the workflow and in each KPI, and it never reports a confidence.

## Tests

```bash
python -m pytest -q
```

129 tests: notebook components, all 8 scenarios through the real pipeline, thermal-control effects, cleaning and tilt
workflows (success **and** failure), verification, classifier adapter (including a model trained on the pipeline's own features,
corrupt / mismatched model files), message envelope, REST/WebSocket API, and real MQTT round-trips against an embedded
broker (`amqtt`, test-only; those two tests skip if it is not installed). The tests assert expected values - there are no hard-coded "PASSED" flags.

## Implemented vs simulated vs pending

| Component | Status |
|---|---|
| Virtual INA219 / BH1750 / AMG8833 | **Simulated** (software-generated) |
| Feature preparation (19-feature I-V schema) | Implemented - I-V curve is **synthesised** from the operating point |
| ML classifier | **Simulated stand-in** now; trained-model adapter implemented and tested with a stand-in model, **pending the real model files** |
| Hotspot detector | Implemented (notebook rules; thresholds provisional) |
| Expected power / health / energy loss | Implemented (notebook model; provisional metrics) |
| Decision engine | Implemented (notebook rules; thresholds configurable) |
| Cleaning and tilting | **Simulated** (software actuator, explicit recovery assumptions) |
| Post-action verification | Implemented on simulated readings; can fail |
| MQTT | Implemented (paho client, reconnect, envelope). Verified against an embedded test broker; **not yet exercised against Mosquitto in this repo's test run** |
| Physical sensors / motors / ESP32 | **Pending** (later semester) |

## Documented simplifications and assumptions

* Thresholds (10 % deviation, 3 cycles, hotspot 65 °C / 15 °C / 2 px, `P_STC` = 30 W, γ = −0.004 /°C, lux factor 0.0079) are the
  notebook's **provisional** values, not validated. All editable at runtime.
* Lux -> irradiance conversion is **uncalibrated**. The simulated lux is derived from the scenario irradiance so the two are consistent.
  (The notebook's own BH1750 scenarios exceed the sensor's nominal 65 535 lx range; the simulation inherits that.)
* Panel model: `P = P_expected x (1 - 2 % baseline) x (1 - 0.30 x soiling) x (1 - 0.80 x shaded fraction) x noise`. Dust adds up to 6.5 °C;
  shade cools its region by 4-10 °C. All in `config.py`.
* Cleaning removes `cleaning_effectiveness` (default 100 %) of the dust. Tilt recovers `tilt_efficacy` (default 85 %) of the shading loss
  for a 30° change, scaled linearly; target angle 120° is an **assumption** (the notebook's `simulate_tilt` modelled no power change).
  Recovery is simulated, never a physical result.
* Verification: mean |deviation| of the next 2 readings below 10 %. After a failed verification the same action is not auto-repeated.
* Documented extensions to the notebook decision engine (rules unchanged): `base_action`/`base_status` are returned next to the hotspot
  overlay; a hotspot alert is still raised if the ML class is unavailable; NaN deviations and a deviation of exactly 0 are handled.
  The notebook's persistence counter lived in a twin recreated on every call; here one stateful twin persists across cycles.
* A hotspot alert suppresses the automatic cleaning/tilt (notebook behaviour). The operator can still run either manually.
* The simulated classifier is a stand-in; its outputs say nothing about the real model's accuracy. The notebook reports 3-class LOO accuracy
  of 0.29 on 7 samples - not a validated performance figure.
* The Wokwi tilting project is **not** part of this website and is not connected.
