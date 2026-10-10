import { api } from '../../api.js'
import { simClock } from '../../format.js'
import Icon from '../ui/Icon.jsx'

export default function Topbar({ s, onMenu }) {
  const { mqtt, classifier, sim, connected } = s
  const live = mqtt?.connected
  const mode = classifier?.mode
  return (
    <header className="topbar">
      <div className="topbar-row">
        <button className="icon-btn menu" onClick={onMenu} aria-label="Open navigation" aria-controls="main-nav"><Icon name="menu" /></button>

        <label className="scenario-select">
          <span>Scenario</span>
          <select value={s.scenarioId} onChange={(e) => api.scenario(e.target.value)} aria-label="Quick scenario switch">
            {s.scenarios.map((sc, i) => <option key={sc.id} value={sc.id}>{i + 1}. {sc.name}</option>)}
          </select>
        </label>

        <div className="sim-controls" role="group" aria-label="Simulation controls">
          {sim?.playing
            ? <button className="btn" aria-label="Pause simulation" onClick={() => api.sim('pause')}><Icon name="pause" size={16} /><span className="lbl">Pause</span></button>
            : <button className="btn primary" aria-label="Run simulation" onClick={() => api.sim('play')}><Icon name="play" size={16} /><span className="lbl">Run</span></button>}
          <button className="btn" aria-label="Step one cycle" onClick={() => api.sim('step')} title="Advance one simulation cycle"><Icon name="step" size={16} /><span className="lbl">Step</span></button>
          <button className="btn" aria-label="Reset simulation" onClick={() => api.sim('reset')} title="Clear history and restart the clock"><Icon name="reset" size={16} /><span className="lbl">Reset</span></button>
        </div>

        <div className="clock" title="Simulation clock - one cycle = configurable simulated minutes">
          <small>SIM TIME</small>
          <strong>{simClock(sim?.sim_time)}</strong>
          <small>cycle {sim?.tick ?? 0}</small>
        </div>
      </div>

      <div className="strip" aria-label="System status">
        <span className="chip sim" title="No physical sensor or actuator is connected to this website.">Simulation · all readings simulated</span>
        <span className={`chip ${live ? 'ok' : 'warn'}`}
          title={live ? 'Messages travel through the MQTT broker.' : `Messages are delivered in-process, not over MQTT. ${mqtt?.last_error || ''}`}>
          {live ? `MQTT broker live · ${mqtt.host}:${mqtt.port}` : 'MQTT: local simulation mode'}
        </span>
        <span className={`chip ${mode === 'trained_model' ? 'ok' : mode === 'unavailable' ? 'alert' : 'info'}`} title={classifier?.error || classifier?.fallback_reason || ''}>
          {mode === 'trained_model' ? `Trained model · ${classifier.name}` : mode === 'unavailable' ? 'Classifier unavailable' : 'Classifier: simulated stand-in'}
        </span>
        {!connected && <span className="chip alert" role="alert">Backend disconnected - retrying…</span>}
      </div>
    </header>
  )
}
