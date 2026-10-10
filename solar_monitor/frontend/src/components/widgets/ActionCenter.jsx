import { useState } from 'react'
import { api } from '../../api.js'
import { actionBusy, f } from '../../format.js'
import Icon from '../ui/Icon.jsx'

const CAT_ORDER = ['Corrective actions', 'Weather & environment', 'Time of day', 'Faults & conditions']
const QUICK = ['clean', 'tilt', 'flat', 'dust_storm', 'rain', 'cloud', 'heat_wave', 'hotspot_on']

// Options worth trying right now, derived from the current situation.
function suggest(s) {
  const r = s.result
  if (!r) return []
  const d = r.decision, hs = r.thermal.hotspot_detected === 'YES'
  const out = []
  if (d.base_action === 'START_CLEANING') out.push({ id: 'clean', why: 'Soiling confirmed - the decision engine wants a cleaning.' })
  else if (d.ml_class === 'Soiling_Dusty') out.push({ id: 'clean', why: 'Dust detected - clean now instead of waiting.' })
  if (d.base_action === 'TILT_PANEL') out.push({ id: 'tilt', params: { angle: 120 }, why: 'Shading detected - lean toward the sun to shrink the shadow.' })
  if (hs) out.push({ id: 'hotspot_off', why: 'Hotspot alert - simulate repairing the faulty cell.' })
  if ((s.truth?.tilt_angle_deg ?? 90) !== 90) out.push({ id: 'flat', why: 'Panel is tilted - return it to the default position.' })
  if (out.length === 0) {
    out.push({ id: 'dust_storm', why: 'Everything is healthy - see how dust changes the diagnosis.' })
    out.push({ id: 'cloud', why: 'A passing cloud lowers power but is not a fault.' })
    out.push({ id: 'tilt', params: { angle: 120 }, why: 'Rotate the panel and watch the 3D rig move.' })
  }
  return out.slice(0, 3)
}

export default function ActionCenter({ s, compact = false, onMore }) {
  const catalog = s.catalog || []
  const byId = Object.fromEntries(catalog.map((e) => [e.id, e]))
  const [vals, setVals] = useState({})
  const [note, setNote] = useState(null)
  const busy = actionBusy(s.action)
  const effects = s.truth?.effects || []

  const paramsFor = (ev) => Object.fromEntries((ev.params || []).map((p) => [p.key, vals[`${ev.id}.${p.key}`] ?? p.default]))
  const run = (id, params) => {
    const ev = byId[id]
    api.event(id, params ?? paramsFor(ev))
      .then((r) => setNote({ tone: 'ok', text: `${r.message} - watch the 3D view.` }))
      .catch((e) => setNote({ tone: 'bad', text: e.message }))
  }
  const disabled = (ev) => ev.kind === 'actuator' && busy
  const sug = suggest(s)

  if (!catalog.length) return <p className="empty">Loading options…</p>

  return (
    <div className={`action-center ${compact ? 'compact' : ''}`}>
      {effects.length > 0 && (
        <div className="effects" aria-live="polite">
          <span className="effects-title">Active now</span>
          {effects.map((e) => <span key={e.id} className="chip info"><Icon name={byId[e.id]?.icon || 'spark'} size={14} /> {e.label} · {f(e.remaining_s, 0)} s</span>)}
        </div>
      )}

      <div className="suggest">
        <h3><Icon name="spark" size={15} /> Suggested for the current situation</h3>
        <div className="suggest-list">
          {sug.map((x) => {
            const ev = byId[x.id]
            if (!ev) return null
            const label = x.id === 'tilt' ? `Rotate to ${x.params.angle}°` : ev.label
            return (
              <button key={x.id} className="suggest-item" disabled={disabled(ev)} onClick={() => run(x.id, x.params)}>
                <span className="opt-ico"><Icon name={ev.icon} /></span>
                <span className="opt-text"><strong>{label}</strong><small>{x.why}</small></span>
                <Icon name="arrow" size={16} />
              </button>
            )
          })}
        </div>
      </div>

      {compact ? (
        <>
          <h3 className="sub">Quick actions</h3>
          <div className="quick">
            {QUICK.map((id) => {
              const ev = byId[id]
              if (!ev) return null
              return (
                <button key={id} className="quick-btn" disabled={disabled(ev)} onClick={() => run(id)}
                  title={`${ev.description} ${ev.effect}`}>
                  <Icon name={ev.icon} size={18} /><span>{id === 'tilt' ? `Rotate ${paramsFor(ev).angle}°` : ev.label}</span>
                </button>
              )
            })}
          </div>
          {onMore && <button className="btn small more" onClick={onMore}>All {catalog.length} options <Icon name="arrow" size={14} /></button>}
        </>
      ) : (
        CAT_ORDER.map((cat) => {
          const items = catalog.filter((e) => e.category === cat)
          if (!items.length) return null
          return (
            <section key={cat} className="opt-cat" aria-label={cat}>
              <h3 className="sub">{cat}</h3>
              <div className="opts">
                {items.map((ev) => (
                  <div key={ev.id} className="opt">
                    <div className="opt-head">
                      <span className="opt-ico"><Icon name={ev.icon} /></span>
                      <span className="opt-text"><strong>{ev.label}</strong><small>{ev.description}</small></span>
                    </div>
                    {(ev.params || []).map((p) => (
                      <label key={p.key} className="slider mini">
                        <span className="slider-label">{p.label}</span>
                        <output>{vals[`${ev.id}.${p.key}`] ?? p.default}{p.unit}</output>
                        <input type="range" min={p.min} max={p.max} step={p.step} value={vals[`${ev.id}.${p.key}`] ?? p.default}
                          onChange={(e) => setVals({ ...vals, [`${ev.id}.${p.key}`]: Number(e.target.value) })} />
                      </label>
                    ))}
                    <p className="opt-effect">{ev.effect}</p>
                    <button className="btn small" disabled={disabled(ev)} title={disabled(ev) ? 'The actuator is busy' : undefined} onClick={() => run(ev.id)}>
                      <Icon name={ev.icon} size={15} /> {ev.kind === 'timed' ? `Start (${ev.duration_s} s)` : 'Run'}
                    </button>
                  </div>
                ))}
              </div>
            </section>
          )
        })
      )}

      <p className={`note ${note?.tone === 'bad' ? 'warn' : note ? 'good' : ''}`} role="status" aria-live="polite" hidden={!note}>{note?.text}</p>
      <p className="hint">What-if options change the <strong>simulated</strong> world; the pipeline reacts only through the resulting sensor readings. Effects are simulation assumptions, not measurements.</p>
    </div>
  )
}
