import { api } from '../../api.js'
import { Pill } from '../ui/Card.jsx'

export function ClassifierPanel({ s }) {
  const c = s.classifier
  return (
    <div>
      <dl className="facts">
        <div><dt>Mode</dt><dd><Pill tone={c?.mode === 'trained_model' ? 'ok' : c?.mode === 'unavailable' ? 'alert' : 'sim'}>{c?.mode === 'simulated' ? 'Simulated stand-in' : c?.mode === 'trained_model' ? 'Trained model' : 'Unavailable'}</Pill></dd></div>
        {c?.name && <div><dt>Name</dt><dd>{c.name}</dd></div>}
        {c?.fallback_reason && <div><dt>Why</dt><dd>{c.fallback_reason}</dd></div>}
        {c?.error && <div><dt>Error</dt><dd className="bad">{c.error}</dd></div>}
        <div><dt>Model folder</dt><dd className="mono">{c?.models_dir}</dd></div>
        <div><dt>Expected file</dt><dd className="mono">{c?.expected_file}</dd></div>
      </dl>
      {c?.mode === 'trained_model' && (
        <p className="hint">Training samples: {c.n_training_samples ?? '?'} · evaluation: {c.evaluation_method ?? '?'}. {(c.caveats || []).join(' ')}</p>
      )}
      <p className="hint">To connect the trained model, copy <span className="mono">solar_panel_condition_model.joblib</span>, <span className="mono">model_metadata.json</span> and <span className="mono">feature_schema.json</span> into the model folder, then reload.</p>
      <button className="btn" onClick={() => api.reloadClassifier()}>Reload model from folder</button>
    </div>
  )
}

export function MqttStatusPanel({ s }) {
  const m = s.mqtt || {}
  return (
    <div>
      <dl className="facts">
        <div><dt>Mode</dt><dd><Pill tone={m.connected ? 'ok' : 'warn'}>{m.connected ? 'MQTT broker - live' : 'Local simulation mode'}</Pill></dd></div>
        <div><dt>Broker</dt><dd className="mono">{m.host}:{m.port}</dd></div>
        {m.last_error && <div><dt>Last status</dt><dd>{m.last_error}</dd></div>}
      </dl>
      <p className="hint">Install Mosquitto and start it with <span className="mono">mosquitto/mosquitto.conf</span>; the app connects automatically (auto-reconnect). Topics: <span className="mono">solar/panel/data · status · command · feedback</span>.</p>
    </div>
  )
}
