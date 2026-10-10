import { useEffect, useRef, useState } from 'react'
import { api } from '../../api.js'
import { f } from '../../format.js'

const SLIDERS = [
  ['irradiance_Wm2', 'Irradiance', 'W/m²', 0, 1200, 10, 0],
  ['background_temp_C', 'Background temperature', '°C', 10, 70, 0.5, 1],
  ['soiling_level', 'Soiling (dust) level', '', 0, 1, 0.01, 2],
  ['shading_fraction', 'Shaded area', '', 0, 0.9, 0.01, 2],
]
const HOT = [
  ['hotspot_peak_C', 'Hotspot peak temperature', '°C', 40, 130, 1, 0],
  ['hotspot_pixels', 'Affected area', 'pixels', 1, 16, 1, 0],
  ['hotspot_row', 'Row', '', 0, 7, 1, 0],
  ['hotspot_col', 'Column', '', 0, 7, 1, 0],
]

export default function ControlsPanel({ s }) {
  const [p, setP] = useState(s.params)
  const [err, setErr] = useState('')
  const lastEdit = useRef(0)
  const timers = useRef({})

  useEffect(() => { if (Date.now() - lastEdit.current > 400) setP(s.params) }, [s.params])

  const set = (key, value) => {
    lastEdit.current = Date.now()
    setP((q) => ({ ...q, [key]: value }))
    clearTimeout(timers.current[key])
    timers.current[key] = setTimeout(() => {
      api.params({ [key]: value }).then(() => setErr('')).catch((e) => setErr(e.message))
    }, 120)
  }

  const row = ([key, label, unit, min, max, step, dec]) => (
    <label className="slider" key={key}>
      <span className="slider-label">{label}</span>
      <output>{f(p[key], dec)} {unit}</output>
      <input type="range" min={min} max={max} step={step} value={p[key] ?? min} onChange={(e) => set(key, Number(e.target.value))} />
    </label>
  )

  return (
    <div>
      <p className="hint top">Base scenario: <strong>{s.scenarioLabel}</strong>. Sliders feed the virtual sensors directly; the next cycle runs the whole pipeline on the new data.</p>
      <div className="slider-grid">{SLIDERS.map(row)}</div>
      <h3 className="sub">Thermal hotspot</h3>
      <label className="check">
        <input type="checkbox" checked={!!p.hotspot_enabled} onChange={(e) => set('hotspot_enabled', e.target.checked)} />
        <span>Inject a hotspot into the 8×8 thermal grid</span>
      </label>
      <fieldset className="slider-grid" disabled={!p.hotspot_enabled}>{HOT.map(row)}</fieldset>
      {err && <p className="error" role="alert">{err}</p>}
    </div>
  )
}
