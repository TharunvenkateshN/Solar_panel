import { useEffect, useRef, useState } from 'react'
import { PanelScene } from '../../three/PanelScene.js'
import { actionBusy, f } from '../../format.js'

const VIEWS = [['perspective', 'Perspective'], ['side', 'Side (angle)'], ['top', 'Top']]

// Maps the live simulation state onto the 3D scene.
function derive(s, thermalOn) {
  const truth = s.truth || {}
  const a = s.action || {}
  const t = s.result?.thermal
  const cleaning = actionBusy(a) && a.action === 'START_CLEANING'
  return {
    tilt: truth.tilt_angle_deg ?? 90,
    dust: truth.effective_soiling ?? 0,
    shade: truth.effective_shading ?? 0,
    sweep: cleaning ? (a.progress ?? 0) / 100 : -1,
    eff: s.config?.cleaning_effectiveness ?? 1,
    weather: truth.weather || {},
    light: (truth.irradiance_effective ?? truth.params?.irradiance_Wm2 ?? 900) / 1000,
    thermalOn,
    hotspot: t?.hotspot_detected === 'YES',
    thermal: t ? { grid: t.grid, hot: t.hotspot_detected === 'YES' ? t.hot_pixels : [] } : null,
  }
}

export default function PanelViewer({ s, size = 'md' }) {
  const host = useRef(null)
  const scene = useRef(null)
  const [view, setView] = useState('perspective')
  const [thermal, setThermal] = useState(false)
  const [spin, setSpin] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    try { scene.current = new PanelScene(host.current); window.__solarScene = scene.current } catch (e) { setErr(e.message || String(e)) }
    return () => { scene.current?.dispose(); scene.current = null }
  }, [])
  useEffect(() => { scene.current?.setView(view) }, [view])
  useEffect(() => { scene.current?.setAutoRotate(spin) }, [spin])
  useEffect(() => { scene.current?.update(derive(s, thermal)) })

  const a = s.action || { phase: 'idle' }
  const busy = actionBusy(a)
  const tilt = s.truth?.tilt_angle_deg ?? 90
  const dust = (s.truth?.effective_soiling ?? 0) * 100
  const shade = (s.truth?.effective_shading ?? 0) * 100
  const verb = a.action === 'TILT_PANEL' ? 'Tilting' : 'Cleaning'

  return (
    <div className={`viewer h-${size}`}>
      <div ref={host} className="viewer-canvas" role="img"
        aria-label={`3D view of the simulated solar panel. Tilt ${f(tilt, 0)} degrees, dust ${f(dust, 0)} percent, shade ${f(shade, 0)} percent.`} />
      {err && <div className="viewer-error"><strong>3D view unavailable.</strong><span>{err}</span><span>The rest of the dashboard still works - WebGL is required for this view.</span></div>}

      <div className="viewer-top">
        <span className="pill sim">SIMULATED 3D - no physical rig</span>
        <div className="seg" role="group" aria-label="Camera view">
          {VIEWS.map(([id, label]) => (
            <button key={id} className={view === id ? 'on' : ''} aria-pressed={view === id} onClick={() => setView(id)}>{label}</button>
          ))}
        </div>
        <div className="seg" role="group" aria-label="Display options">
          <button className={thermal ? 'on' : ''} aria-pressed={thermal} onClick={() => setThermal(!thermal)} title="Drape the simulated 8×8 thermal grid over the cells">Thermal overlay</button>
          <button className={spin ? 'on' : ''} aria-pressed={spin} onClick={() => setSpin(!spin)}>Auto-rotate</button>
        </div>
      </div>

      {(s.truth?.effects || []).length > 0 && (
        <div className="viewer-effects" aria-live="polite">
          {s.truth.effects.map((e) => <span key={e.id} className="chip info">{e.label} · {f(e.remaining_s, 0)} s</span>)}
        </div>
      )}

      <div className="viewer-hud" aria-live="polite">
        <div className="hud-row">
          <span><b>{f(tilt, 0)}°</b> servo angle</span>
          <span><b>{f(dust, 0)}%</b> dust</span>
          <span><b>{f(shade, 0)}%</b> shaded</span>
        </div>
        {busy ? (
          <div className="hud-progress" role="progressbar" aria-valuenow={a.progress ?? 0} aria-valuemin={0} aria-valuemax={100} aria-label={`${verb} progress`}>
            <div className="bar"><i style={{ width: `${a.progress ?? 0}%` }} /></div>
            <span>{verb} {a.progress ?? 0}%</span>
          </div>
        ) : (
          <span className="hud-idle">Actuator {a.phase === 'completed' ? 'finished' : 'idle'} · drag to orbit, scroll to zoom</span>
        )}
      </div>
    </div>
  )
}
