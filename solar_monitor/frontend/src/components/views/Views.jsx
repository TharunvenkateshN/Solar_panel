import { Card, PageHeader, Pill } from '../ui/Card.jsx'
import StatusBanner from '../widgets/StatusBanner.jsx'
import KpiGrid from '../widgets/KpiGrid.jsx'
import PanelViewer from '../widgets/PanelViewer.jsx'
import Workflow, { StageRail } from '../widgets/Workflow.jsx'
import ScenarioPicker from '../widgets/ScenarioPicker.jsx'
import ControlsPanel from '../widgets/ControlsPanel.jsx'
import ActionCenter from '../widgets/ActionCenter.jsx'
import BeforeAfter from '../widgets/BeforeAfter.jsx'
import ThermalGrid from '../widgets/ThermalGrid.jsx'
import DecisionRules from '../widgets/DecisionRules.jsx'
import EventLog from '../widgets/EventLog.jsx'
import MqttMonitor from '../widgets/MqttMonitor.jsx'
import ConfigPanel from '../widgets/ConfigPanel.jsx'
import { ClassifierPanel, MqttStatusPanel } from '../widgets/SystemPanels.jsx'
import { DeviationChart, IvCurve, MarkerLegend, PowerChart, TempChart } from '../widgets/Charts.jsx'
import { f } from '../../format.js'

export function OverviewView({ s, go }) {
  return (
    <>
      <PageHeader title="Overview" subtitle="Live state of the simulated panel and what the system decided." />
      <StatusBanner s={s} />
      <div className="grid two-wide">
        <Card title="Live 3D panel" sim id="ov-3d" className="fill" actions={<button className="btn small" onClick={() => go('panel')}>Open full view</button>}>
          <PanelViewer s={s} size="fill" />
        </Card>
        <Card title="Try an action" sim id="ov-actions">
          <ActionCenter s={s} compact onMore={() => go('panel')} />
        </Card>
      </div>
      <div className="grid two">
        <Card title="Pipeline" sim id="ov-rail" actions={<button className="btn small" onClick={() => go('workflow')}>Details</button>}>
          <StageRail s={s} onOpen={() => go('workflow')} />
        </Card>
        <Card title="Latest events" id="ov-events" actions={<button className="btn small" onClick={() => go('events')}>All events</button>}>
          <EventLog s={s} limit={16} maxHeight="none" compact />
        </Card>
      </div>
      <KpiGrid s={s} />
    </>
  )
}

export function ScenariosView({ s }) {
  const r = s.result
  const tr = s.truth
  return (
    <>
      <PageHeader title="Scenarios & controls" subtitle="Choose a situation or build your own. The class, hotspot result and action are derived from the simulated sensor data, never looked up." />
      <Card title="Scenario" id="sc-pick"><ScenarioPicker s={s} /></Card>
      <div className="grid two">
        <Card title="Simulation controls" sim id="sc-controls"><ControlsPanel s={s} /></Card>
        <div className="stack">
          <Card title="What the pipeline derived" id="sc-derived">
            {r ? (
              <dl className="facts">
                <div><dt>Status</dt><dd>{r.decision.final_status.replace(/_/g, ' ').toLowerCase()}</dd></div>
                <div><dt>ML class</dt><dd>{r.decision.ml_class.replace(/_/g, ' ')}</dd></div>
                <div><dt>Hotspot</dt><dd>{r.thermal.hotspot_detected}</dd></div>
                <div><dt>Deviation</dt><dd>{f(r.twin.deviation_pct, 1)}% (persistence {Math.min(r.twin.persist_count, r.twin.persist_required)}/{r.twin.persist_required})</dd></div>
                <div><dt>Action</dt><dd>{r.decision.recommended_action.replace(/_/g, ' ').toLowerCase()}</dd></div>
              </dl>
            ) : <p className="empty">Waiting for a reading…</p>}
          </Card>
          <Card title="Simulator internals" sim id="sc-truth">
            <p className="hint top">Ground truth the simulator uses to generate sensor data. The pipeline never sees these values.</p>
            {tr && (
              <dl className="facts">
                <div><dt>Effective soiling</dt><dd>{f(tr.effective_soiling * 100, 0)}% <small>(cleaned fraction {f(tr.cleaned_fraction * 100, 0)}%)</small></dd></div>
                <div><dt>Effective shading</dt><dd>{f(tr.effective_shading * 100, 0)}% <small>of panel area</small></dd></div>
                <div><dt>Servo angle</dt><dd>{f(tr.tilt_angle_deg, 0)}° <small>(90° = default)</small></dd></div>
              </dl>
            )}
          </Card>
        </div>
      </div>
    </>
  )
}

export function PanelView({ s }) {
  return (
    <>
      <PageHeader title="3D panel & actions" subtitle="Watch the cleaning robot and the tilt mechanism work on the simulated panel." />
      <div className="grid two-wide top panel-layout">
        <div className="sticky-col">
          <Card title="Simulated panel rig" sim id="p-3d">
            <PanelViewer s={s} size="lg" />
          </Card>
        </div>
        <Card title="Actions & what-if events" sim id="p-act">
          <ActionCenter s={s} />
        </Card>
      </div>
      <div className="grid two">
        <Card title="Before vs after action" sim id="p-ba"><BeforeAfter s={s} /></Card>
        <Card title="Latest events" id="p-ev"><EventLog s={s} limit={10} maxHeight={300} compact /></Card>
      </div>
    </>
  )
}

export function ThermalView({ s }) {
  const r = s.result
  const ina = r?.electrical
  const iv = r?.features?.iv_features
  return (
    <>
      <PageHeader title="Thermal & sensors" subtitle="The 8×8 thermal grid, the hotspot rules and the virtual sensor readings." />
      <div className="grid two">
        <Card title="Thermal grid - AMG8833" sim id="t-grid"><ThermalGrid s={s} /></Card>
        <div className="stack">
          <Card title="Hotspot detector" id="t-rules">
            {r && (
              <dl className="facts">
                <div><dt>Result</dt><dd className={r.thermal.hotspot_detected === 'YES' ? 'bad' : 'good'}>{r.thermal.hotspot_detected}</dd></div>
                <div><dt>Max / mean</dt><dd>{f(r.thermal.max_temp_C)} / {f(r.thermal.mean_temp_C)} °C</dd></div>
                <div><dt>Absolute rule</dt><dd>max &gt; {r.thermal.thresholds.abs_thresh} °C - {r.thermal.cond_abs_triggered ? 'triggered' : 'not triggered'}</dd></div>
                <div><dt>Delta rule</dt><dd>max − mean &gt; {r.thermal.thresholds.delta_thresh} °C and ≥ {r.thermal.thresholds.hot_px_thresh} hot px - {r.thermal.cond_delta_triggered ? 'triggered' : 'not triggered'}</dd></div>
                <div><dt>Note</dt><dd>Thresholds are provisional, not calibrated. Independent of the ML class.</dd></div>
              </dl>
            )}
          </Card>
          <Card title="Virtual sensors" sim id="t-sens">
            {r && (
              <dl className="facts">
                <div><dt>INA219</dt><dd>{f(ina.voltage_V, 2)} V × {f(ina.current_A, 3)} A = {f(ina.power_W, 2)} W</dd></div>
                <div><dt>BH1750</dt><dd>{f(r.lux, 0)} lx <small>≈ {f(r.irradiance_Wm2, 0)} W/m² ({r.irradiance_source.replace(/_/g, ' ').toLowerCase()})</small></dd></div>
                <div><dt>Panel temperature</dt><dd>{f(r.panel_temp_C)} °C <small>mean of the thermal grid</small></dd></div>
              </dl>
            )}
          </Card>
        </div>
      </div>
      <div className="grid two">
        <Card title="Synthesised I-V curve" sim id="t-iv">
          <IvCurve s={s} />
          <p className="hint">No I-V sweep hardware exists, so the curve is synthesised from the simulated operating point. It feeds the 19-feature schema used by the classifier.</p>
        </Card>
        <Card title="Classifier features" sim id="t-feat">
          {iv && (
            <div className="feature-grid">
              {Object.entries(iv).map(([k, v]) => <div key={k}><span>{k.replace(/_/g, ' ')}</span><b>{f(v, 2)}</b></div>)}
            </div>
          )}
        </Card>
      </div>
    </>
  )
}

export function WorkflowView({ s }) {
  return (
    <>
      <PageHeader title="Workflow" subtitle="Virtual sensors → features → ML → hotspot → expected power → decision → action → verification." />
      <Card title="Pipeline stages" sim id="w-stages"><Workflow s={s} /></Card>
      <Card title="Decision rules" id="w-rules"><DecisionRules s={s} /></Card>
    </>
  )
}

export function AnalyticsView({ s }) {
  return (
    <>
      <PageHeader title="Analytics" subtitle="Trends over the simulation run. History is generated by the simulation." />
      <div className="grid two">
        <Card title="Power - measured vs expected" sim id="a-power"><PowerChart s={s} /></Card>
        <Card title="Deviation & health" sim id="a-dev"><DeviationChart s={s} /></Card>
        <Card title="Temperature trends" sim id="a-temp"><TempChart s={s} /></Card>
        <Card title="Before vs after action" sim id="a-ba"><BeforeAfter s={s} /></Card>
      </div>
      <MarkerLegend />
    </>
  )
}

export function EventsView({ s }) {
  return (
    <>
      <PageHeader title="Events & MQTT" subtitle="Everything that happened, and the messages exchanged between the components." />
      <div className="grid two">
        <Card title="Event history" id="e-log"><EventLog s={s} maxHeight={560} /></Card>
        <Card title="MQTT message monitor" id="e-mqtt"><MqttMonitor s={s} maxHeight={560} /></Card>
      </div>
    </>
  )
}

export function SettingsView({ s }) {
  return (
    <>
      <PageHeader title="Settings" subtitle="Thresholds, simulated actuator assumptions, classifier and MQTT." />
      <Card title="Configuration" rt id="s-config"><ConfigPanel s={s} /></Card>
      <div className="grid two">
        <Card title="Classifier" id="s-clf"><ClassifierPanel s={s} /></Card>
        <Card title="MQTT" id="s-mqtt"><MqttStatusPanel s={s} /></Card>
      </div>
    </>
  )
}

const ROWS = [
  ['Virtual INA219 / BH1750 / AMG8833', 'Simulated', 'Software-generated readings (ported from the notebook).'],
  ['Feature preparation', 'Implemented', '19-feature I-V schema; the I-V curve is synthesised from the operating point.'],
  ['ML classifier', 'Simulated', 'Rule-based stand-in. Copy the trained .joblib into backend/models and reload from Settings.'],
  ['Hotspot detector', 'Implemented', 'Notebook rules, independent of the ML class.'],
  ['Expected power / digital twin', 'Implemented', 'Notebook model; health and energy loss are provisional.'],
  ['Decision engine', 'Implemented', 'Notebook rules plus persistence; thresholds configurable.'],
  ['Cleaning & tilting', 'Simulated', 'Software actuators with explicit recovery assumptions. No motor is controlled.'],
  ['3D view', 'Simulated', 'Visualises the simulator state (tilt, dust, shade, thermal). Not a physical measurement.'],
  ['Post-action verification', 'Implemented', 'Runs on the simulated post-action readings; it can fail.'],
  ['MQTT', 'Implemented', 'Real paho client and broker round-trip when Mosquitto runs; otherwise labelled local mode.'],
  ['Hardware integration', 'Pending', 'Planned for a later semester.'],
]

export function AboutView({ s }) {
  return (
    <>
      <PageHeader title="About" subtitle="Intelligent solar panel monitoring, self-adaptive cleaning and predictive fault diagnosis using IoT and ML." />
      <Card title="Implemented, simulated and pending" id="ab-table">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Component</th><th>Status</th><th>Notes</th></tr></thead>
            <tbody>
              {ROWS.map(([a, b, c]) => (
                <tr key={a}><td><strong>{a}</strong></td><td><Pill tone={b === 'Implemented' ? 'ok' : b === 'Simulated' ? 'sim' : 'muted'}>{b}</Pill></td><td>{c}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title="Good to know" id="ab-notes">
        <ul className="bullets">
          <li>Every sensor reading, the I-V curve, the cleaning / tilt recovery and the history are <strong>simulated</strong>.</li>
          <li>Thresholds (10 % deviation, 3 cycles, hotspot 65 °C / 15 °C / 2 px) are the notebook's <strong>provisional</strong> values.</li>
          <li>The classifier is a stand-in until the trained model files are added; it reports no confidence. The notebook's 3-class model used only 7 samples, so its accuracy must not be cited as validated.</li>
          <li>A hotspot alert never erases the ML class and suppresses automatic cleaning / tilting; the operator can still run either manually.</li>
          <li>Recovery after cleaning or tilting is a simulation assumption, not a physical experiment. Verification can fail and then says so.</li>
        </ul>
      </Card>
    </>
  )
}
