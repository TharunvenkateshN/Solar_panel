import { f, heat } from '../../format.js'

export default function ThermalGrid({ s, size = 440 }) {
  const t = s.result?.thermal
  if (!t) return null
  const flat = t.grid.flat()
  const lo = Math.min(30, ...flat), hi = Math.max(80, ...flat)
  const hot = new Set(t.hot_pixels.map(([r, c]) => `${r},${c}`))
  const fired = [t.cond_abs_triggered && `max > ${t.thresholds.abs_thresh} °C`,
    t.cond_delta_triggered && `max − mean > ${t.thresholds.delta_thresh} °C and ≥ ${t.thresholds.hot_px_thresh} hot pixels`].filter(Boolean)
  return (
    <div className="thermal-wrap" style={{ maxWidth: size }}>
      <div className="thermal" role="table" aria-label="8 by 8 thermal grid, degrees Celsius">
        {t.grid.map((row, r) => row.map((v, c) => {
          const col = heat(v, lo, hi)
          const isHot = hot.has(`${r},${c}`)
          return (
            <div key={`${r}-${c}`} role="cell" className={`cell ${isHot ? 'hot' : ''}`} style={{ background: col.bg, color: col.fg }}
              title={`pixel (${r}, ${c}): ${v.toFixed(2)} °C${isHot ? ` - above hot threshold ${f(t.hot_threshold_C)} °C` : ''}`}>
              {v.toFixed(0)}{isHot && <b aria-label="hot pixel">▲</b>}
            </div>
          )
        }))}
      </div>
      <div className="legend"><span>{lo.toFixed(0)} °C</span><div className="ramp" /><span>{hi.toFixed(0)} °C</span></div>
      <dl className="facts">
        <div><dt>Hotspot</dt><dd className={t.hotspot_detected === 'YES' ? 'bad' : 'good'}>{t.hotspot_detected}</dd></div>
        <div><dt>Hot pixels (▲)</dt><dd>{t.hot_pixel_count} <small>above mean + 2σ = {f(t.hot_threshold_C)} °C</small></dd></div>
        <div><dt>Rule fired</dt><dd>{fired.length ? fired.join(' · ') : 'none'}</dd></div>
      </dl>
    </div>
  )
}
