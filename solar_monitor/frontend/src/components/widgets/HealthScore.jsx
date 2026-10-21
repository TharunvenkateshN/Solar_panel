import { f } from '../../format.js'

const TONE = { Healthy: 'ok', Degraded: 'warn', Critical: 'alert' }
const ROWS = [
  ['power_deviation', 'Power deviation'],
  ['hotspot', 'Hotspot'],
  ['partial_shading', 'Partial shading'],
  ['soiling', 'Soiling'],
]

// Panel Health Score from the pipeline (backend composite_health). A simulated estimate, not a measurement.
export default function HealthScore({ s }) {
  const h = s.result?.twin?.health
  if (!h) return <p className="empty">Waiting for a reading…</p>
  const tone = TONE[h.status] || 'muted'
  return (
    <div className={`health ${tone}`}>
      <div className="health-top">
        <div className="health-score" aria-label={`Panel health score ${f(h.score, 0)} percent, ${h.status}`}>
          <span className="health-num">{f(h.score, 0)}</span><small>%</small>
        </div>
        <span className={`pill ${tone}`}>{h.status}</span>
      </div>
      <div className="health-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(h.score)}>
        <i style={{ width: `${h.score}%` }} />
      </div>
      <dl className="health-parts">
        {ROWS.map(([k, label]) => (
          <div key={k} className={h.penalties[k] > 0 ? 'on' : ''}><dt>{label}</dt><dd>{h.penalties[k] > 0 ? `−${f(h.penalties[k], 1)}` : '—'}</dd></div>
        ))}
      </dl>
      <p className="hint" title={h.formula}>Simulated estimate, not a validated measurement. Score = 100 minus the penalties above (≥ 80 healthy, 50–79 degraded, &lt; 50 critical).</p>
    </div>
  )
}
