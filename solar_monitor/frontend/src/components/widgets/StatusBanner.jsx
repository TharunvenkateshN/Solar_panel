import { STATUS, actionText, className, f } from '../../format.js'

export default function StatusBanner({ s }) {
  const r = s.result
  if (!r) return <section className="banner muted"><h2>Waiting for the first reading…</h2></section>
  const d = r.decision, t = r.thermal, ml = r.ml
  const st = STATUS[d.final_status] || { label: d.final_status, tone: 'muted', note: '' }
  const hs = t.hotspot_detected === 'YES'
  return (
    <section className={`banner ${st.tone}`} aria-label="Panel operating status">
      <div className="banner-main">
        <span className="eyebrow">Panel operating status</span>
        <h2>{st.label}</h2>
        <p>{st.note}</p>
        <p className="reason">{d.reason}</p>
      </div>
      <dl className="banner-facts">
        <div>
          <dt>ML classification</dt>
          <dd>{className(ml.label)}</dd>
          <small>{ml.mode === 'simulated' ? 'simulated classifier' : ml.mode === 'trained_model' ? 'trained model' : 'unavailable'}</small>
        </div>
        <div>
          <dt>Hotspot</dt>
          <dd className={hs ? 'bad' : 'good'}>{t.hotspot_detected}</dd>
          <small>max {f(t.max_temp_C)} °C</small>
        </div>
        <div>
          <dt>Recommended action</dt>
          <dd>{actionText(d.recommended_action)}</dd>
          <small>{hs ? `underlying: ${actionText(d.base_action).toLowerCase()}` : 'decision engine'}</small>
        </div>
      </dl>
    </section>
  )
}
