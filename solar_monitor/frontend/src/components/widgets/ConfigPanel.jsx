import { useEffect, useState } from 'react'
import { api } from '../../api.js'

const FIELDS = [
  ['Decision engine', [
    ['soiling_dev_thresh_pct', 'Deviation threshold (%)', 'provisional - notebook: 10'],
    ['persist_cycles', 'Consecutive cycles before cleaning', 'provisional - notebook: 3'],
  ]],
  ['Hotspot detector', [
    ['hotspot_abs_thresh_c', 'Absolute max temperature (°C)', 'provisional - 65'],
    ['hotspot_delta_thresh_c', 'Max − mean (°C)', 'provisional - 15'],
    ['hot_pixel_thresh', 'Minimum hot pixels', 'provisional - 2'],
  ]],
  ['Digital twin', [['p_stc_w', 'Rated power P_STC (W)', 'example value - set from the datasheet']]],
  ['Post-action verification', [
    ['verification_dev_thresh_pct', 'Recovered if deviation below (%)', 'simulation assumption'],
    ['verification_cycles', 'Readings averaged', ''],
  ]],
  ['Simulated actuators (assumptions)', [
    ['cleaning_effectiveness', 'Cleaning effectiveness (0-1)', 'lower it to see a FAILED verification'],
    ['cleaning_duration_s', 'Cleaning duration (s)', ''],
    ['tilt_target_angle_deg', 'Tilt target angle (°)', 'assumed'],
    ['tilt_efficacy', 'Tilt efficacy (0-1)', 'max share of shading loss recovered'],
  ]],
  ['Simulation clock', [
    ['tick_interval_s', 'Seconds per cycle', ''],
    ['sim_minutes_per_tick', 'Simulated minutes per cycle', ''],
  ]],
]
const TOGGLES = [
  ['auto_execute', 'Decision engine sends commands automatically'],
  ['actuator_simulator_enabled', 'Built-in actuator simulator answers commands'],
]

export default function ConfigPanel({ s }) {
  const [draft, setDraft] = useState({})
  const [err, setErr] = useState('')
  useEffect(() => setDraft({}), [s.config])
  const val = (k) => (k in draft ? draft[k] : s.config[k] ?? '')
  const send = (changes) => api.config(changes).then(() => setErr('')).catch((e) => setErr(e.message))
  const commit = (k) => { if (k in draft && draft[k] !== '') send({ [k]: Number(draft[k]) }) }
  return (
    <div>
      <p className="hint top">All thresholds are provisional or simulation assumptions - not experimentally validated. Press Enter or leave a field to apply.</p>
      <div className="toggles">
        {TOGGLES.map(([k, label]) => (
          <label className="check" key={k}>
            <input type="checkbox" checked={!!s.config[k]} onChange={(e) => send({ [k]: e.target.checked })} /><span>{label}</span>
          </label>
        ))}
      </div>
      <div className="config-groups">
        {FIELDS.map(([group, items]) => (
          <fieldset key={group} className="config-group">
            <legend>{group}</legend>
            {items.map(([k, label, note]) => (
              <label className="field" key={k}>
                <span>{label}{note && <small>{note}</small>}</span>
                <input type="number" step="any" value={val(k)} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}
                  onBlur={() => commit(k)} onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()} />
              </label>
            ))}
          </fieldset>
        ))}
      </div>
      {err && <p className="error" role="alert">{err}</p>}
    </div>
  )
}
