import { actionBusy } from '../../format.js'

// Appears on every page while a corrective action runs, so nothing is missed when browsing elsewhere.
export default function ActionBar({ s, route, go }) {
  const a = s.action
  const v = s.verification
  const busy = actionBusy(a)
  const verifying = s.stages?.find((x) => x.id === 'verification')?.state === 'active'
  if (!busy && !verifying) return null
  const verb = a?.action === 'TILT_PANEL' ? 'Tilting' : 'Cleaning'
  return (
    <div className="actionbar" role="status" aria-live="polite">
      <span className="dot running" aria-hidden />
      <strong>{busy ? `${verb} in progress - ${a.progress ?? 0}%` : 'Verifying performance…'}</strong>
      <span className="muted">{busy ? (a.action === 'TILT_PANEL' ? `servo → ${Math.round(s.truth?.tilt_angle_deg ?? 90)}°` : 'brush sweeping the panel') : `collecting post-action readings (${v ? '' : ''}simulated)`}</span>
      {route !== 'panel' && <button className="btn small" onClick={() => go('panel')}>Watch in 3D</button>}
    </div>
  )
}
