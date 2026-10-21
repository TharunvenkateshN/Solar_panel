export const f = (v, d = 1) => (v === null || v === undefined || Number.isNaN(v) ? '—' : Number(v).toFixed(d))
export const simClock = (iso) => (iso ? iso.slice(11, 16) : '--:--')
export const simClockSec = (iso) => (iso ? iso.slice(11, 19) : '--:--:--')
export const wallClock = (iso) => (iso ? new Date(iso).toLocaleTimeString() : '')

export const CLASS_LABEL = {
  Healthy_Clean: 'Healthy · clean',
  Soiling_Dusty: 'Soiling · dusty',
  Partial_Shading: 'Partial shading',
  MODEL_UNAVAILABLE: 'Unavailable',
}
export const className = (c) => CLASS_LABEL[c] || (c ? c.replace(/_/g, ' ') : '—')

export const STATUS = {
  HEALTHY: { label: 'Healthy', tone: 'ok', note: 'Clean panel - no intervention required.' },
  SOILING_DETECTED: { label: 'Soiling condition', tone: 'warn', note: 'Soiling detected; waiting for the degradation to persist.' },
  CLEANING_REQUIRED: { label: 'Soiling - cleaning required', tone: 'warn', note: 'Soiling confirmed over the required number of cycles.' },
  PARTIAL_SHADING: { label: 'Partial shading', tone: 'info', note: 'Tilting / orientation correction requested.' },
  PARTIAL_SHADING_AND_SOILING: { label: 'Partial shading + soiling', tone: 'warn', note: 'ML class: partial shading. Extra power loss indicates soiling too - tilt first, then clean.' },
  HOTSPOT_DETECTED: { label: 'Hotspot alert', tone: 'alert', note: 'Thermal hotspot on an otherwise healthy classification.' },
  HOTSPOT_AND_SOILING: { label: 'Hotspot alert + soiling', tone: 'alert', note: 'Hotspot safety alert raised. ML class stays soiling; automatic cleaning runs when persistence is met (hotspot repair is manual).' },
  HOTSPOT_AND_PARTIAL_SHADING: { label: 'Hotspot alert + partial shading', tone: 'alert', note: 'Underlying classification preserved: partial shading.' },
  MODEL_UNAVAILABLE: { label: 'Classifier unavailable', tone: 'muted', note: 'No valid ML class could be produced.' },
}

export const ACTION_TEXT = {
  NO_ACTION: 'No intervention',
  WAIT: 'Wait',
  START_CLEANING: 'Start cleaning',
  TILT_PANEL: 'Tilt panel',
  HOTSPOT_ALERT: 'Hotspot alert',
  HOTSPOT_ALERT_WITH_SOILING: 'Hotspot alert + soiling',
  HOTSPOT_ALERT_WITH_PARTIAL_SHADING: 'Hotspot alert + shading',
  MODEL_UNAVAILABLE: 'Model unavailable',
}
export const actionText = (a) => ACTION_TEXT[a] || (a ? a.replace(/_/g, ' ').toLowerCase() : '—')

// blue -> teal -> yellow -> orange -> red -> white
const STOPS = [[29, 78, 216], [34, 193, 195], [253, 216, 53], [251, 140, 0], [229, 57, 53], [255, 255, 255]]
export function heat(t, lo, hi) {
  const x = Math.min(1, Math.max(0, (t - lo) / (hi - lo || 1))) * (STOPS.length - 1)
  const i = Math.min(STOPS.length - 2, Math.floor(x))
  const k = x - i
  const c = STOPS[i].map((v, j) => Math.round(v + (STOPS[i + 1][j] - v) * k))
  const lum = (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255
  return { bg: `rgb(${c[0]},${c[1]},${c[2]})`, fg: lum > 0.55 ? '#10151f' : '#ffffff' }
}

// is a corrective action currently running?
export const actionBusy = (a) => !!a && (a.phase === 'running' || a.phase === 'commanded')

// "HOTSPOT_ALERT_WITH_SOILING" -> "Hotspot alert with soiling", "Soiling_Dusty" -> "Soiling dusty"
export function pretty(text) {
  if (text === null || text === undefined) return ''
  const cap = (m) => { const w = m.toLowerCase().replace(/_/g, ' '); return w[0].toUpperCase() + w.slice(1) }
  return String(text)
    .replace(/(?<![A-Za-z0-9_])[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+(?![A-Za-z0-9_])/g, cap)
    .replace(/(?<![A-Za-z0-9_])[A-Z][a-z]+(?:_[A-Z][a-z]+)+(?![A-Za-z0-9_])/g, cap)
}
