import { pretty } from '../../format.js'

const ORDER = ['sensors', 'features', 'ml', 'hotspot', 'twin', 'decision', 'action', 'verification']
const SHORT = { sensors: 'Sensors', features: 'Features', ml: 'ML class', hotspot: 'Hotspot', twin: 'Expected', decision: 'Decision', action: 'Action', verification: 'Verify' }
const STATE_TEXT = { done: 'OK', warn: 'Attention', alert: 'Alert', error: 'Problem', active: 'Running', pending: 'Waiting' }

// Compact one-line rail for the overview page
export function StageRail({ s, onOpen }) {
  const byId = Object.fromEntries((s.stages || []).map((x) => [x.id, x]))
  return (
    <ol className="rail" aria-label="Pipeline stages">
      {ORDER.map((id, i) => {
        const st = byId[id]
        return (
          <li key={id} className={`rail-item ${st?.state || 'pending'}`}>
            <button onClick={() => onOpen?.(id)} title={st ? `${st.title}: ${st.headline}` : id}>
              <span className="rail-step">{i + 1}</span>
              <span className="rail-name">{SHORT[id]}</span>
              <span className="rail-val">{pretty(st?.headline) || '…'}</span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}

// Detailed cards for the workflow page
export default function Workflow({ s }) {
  const byId = Object.fromEntries((s.stages || []).map((x) => [x.id, x]))
  return (
    <ol className="stages">
      {ORDER.map((id, i) => {
        const st = byId[id]
        if (!st) return <li key={id} className="stage pending"><span className="step">{i + 1}</span></li>
        return (
          <li key={id} id={`stage-${id}`} className={`stage ${st.state}`}>
            <div className="stage-head">
              <span className="step">{i + 1}</span>
              <h3>{st.title}</h3>
              <span className={`state-tag ${st.state}`}>{STATE_TEXT[st.state] || st.state}</span>
            </div>
            <div className="stage-headline">{pretty(st.headline)}</div>
            <dl>
              {Object.entries(st.details || {}).map(([k, v]) => (
                <div key={k}><dt>{k}</dt><dd>{pretty(v)}</dd></div>
              ))}
            </dl>
          </li>
        )
      })}
    </ol>
  )
}
