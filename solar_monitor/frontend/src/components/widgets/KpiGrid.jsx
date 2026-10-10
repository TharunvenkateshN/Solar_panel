import { actionBusy, actionText, className, f } from '../../format.js'

function Tile({ label, value, unit, sub, tone }) {
  return (
    <div className={`tile ${tone || ''}`}>
      <span className="tile-label">{label}</span>
      <span className="tile-value">{value}{unit && <small>{unit}</small>}</span>
      {sub && <span className="tile-sub">{sub}</span>}
    </div>
  )
}

function Group({ title, children }) {
  return (
    <div className="kpi-group">
      <h3>{title} <span className="pill sim">SIM</span></h3>
      <div className="kpis">{children}</div>
    </div>
  )
}

export default function KpiGrid({ s }) {
  const r = s.result
  if (!r) return null
  const e = r.electrical, t = r.thermal, tw = r.twin, ml = r.ml, a = s.action
  const dev = tw.deviation_pct
  const devTone = dev === null ? '' : Math.abs(dev) > (s.config.soiling_dev_thresh_pct ?? 10) ? 'warn' : 'ok'
  const hs = t.hotspot_detected === 'YES'
  const busy = actionBusy(a)
  const verb = a?.action === 'TILT_PANEL' ? 'Tilting' : 'Cleaning'
  const actuator = busy ? `${verb} ${a.progress ?? 0}%` : a?.phase === 'completed' ? `${verb === 'Tilting' ? 'Tilt' : 'Cleaning'} done` : 'Idle'
  return (
    <section className="kpi-groups" aria-label="Live readings">
      <Group title="Electrical (INA219)">
        <Tile label="Voltage" value={f(e.voltage_V, 2)} unit="V" />
        <Tile label="Current" value={f(e.current_A, 3)} unit="A" />
        <Tile label="Power measured" value={f(e.power_W, 2)} unit="W" sub="P = V × I" />
        <Tile label="Power expected" value={f(tw.power_expected_W, 2)} unit="W" sub="digital twin" />
        <Tile label="Deviation" value={f(dev, 1)} unit="%" sub={`persistence ${Math.min(tw.persist_count, tw.persist_required)}/${tw.persist_required}`} tone={devTone} />
        <Tile label="Health indicator" value={f(tw.health_score_pct, 1)} unit="%" sub="provisional" />
      </Group>
      <Group title="Environment & thermal">
        <Tile label="Illumination" value={f(r.lux, 0)} unit="lx" sub={`≈ ${f(r.irradiance_Wm2, 0)} W/m² (uncalibrated)`} />
        <Tile label="Panel temperature" value={f(r.panel_temp_C)} unit="°C" sub="mean of thermal grid" />
        <Tile label="Thermal max" value={f(t.max_temp_C)} unit="°C" sub={`pixel (${t.hotspot_row}, ${t.hotspot_col})`} tone={hs ? 'alert' : ''} />
        <Tile label="Thermal average" value={f(t.mean_temp_C)} unit="°C" sub={`max − mean ${f(t.max_minus_mean_C)} °C`} />
      </Group>
      <Group title="Diagnosis & action">
        <Tile label="ML class" value={className(ml.label)} sub={ml.mode === 'simulated' ? 'simulated classifier' : ml.mode} tone={ml.label ? '' : 'alert'} />
        <Tile label="ML confidence" value={ml.confidence !== null ? f(ml.confidence, 2) : 'n/a'} sub={ml.confidence !== null ? 'model probability' : 'trained model only'} />
        <Tile label="Hotspot" value={t.hotspot_detected} sub={`${t.hot_pixel_count} hot pixel(s)`} tone={hs ? 'alert' : 'ok'} />
        <Tile label="Recommended action" value={actionText(r.decision.recommended_action)} />
        <Tile label="Cleaning / tilt" value={actuator} sub={`servo ${f(r.actuators?.tilt_angle_deg, 0)}°`} />
        <Tile label="Alert" value={hs ? 'Hotspot' : 'None'} tone={hs ? 'alert' : 'ok'} />
      </Group>
    </section>
  )
}
