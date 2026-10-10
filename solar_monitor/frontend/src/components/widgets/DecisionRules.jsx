const RULES = [
  { cls: 'Healthy_Clean', hs: 'NO', cond: 'any', action: 'NO_ACTION', result: 'No intervention', match: (d) => d.base_action === 'NO_ACTION' },
  { cls: 'Soiling_Dusty', hs: 'NO', cond: 'below threshold or not persistent', action: 'WAIT', result: 'Wait and keep monitoring', match: (d) => d.base_action === 'WAIT' },
  { cls: 'Soiling_Dusty', hs: 'NO', cond: '≥ threshold and persistent', action: 'START_CLEANING', result: 'Start cleaning', match: (d) => d.base_action === 'START_CLEANING' },
  { cls: 'Partial_Shading', hs: 'NO', cond: 'any', action: 'TILT_PANEL', result: 'Request tilt (never cleaning)', match: (d) => d.base_action === 'TILT_PANEL' },
  { cls: 'any class', hs: 'YES', cond: 'any', action: 'HOTSPOT_ALERT…', result: 'Hotspot alert, underlying class preserved', match: (d) => d.recommended_action.startsWith('HOTSPOT') },
]

export default function DecisionRules({ s }) {
  const d = s.result?.decision
  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr">Decision rules. The row that produced the current decision is highlighted.</caption>
        <thead><tr><th>ML class</th><th>Hotspot</th><th>Deviation / persistence</th><th>Engine output</th><th>Meaning</th></tr></thead>
        <tbody>
          {RULES.map((r, i) => {
            const on = d && r.match(d) && (r.hs === 'YES' ? d.hotspot === 'YES' : d.hotspot !== 'YES')
            return (
              <tr key={i} className={on ? 'on' : ''} aria-current={on ? 'true' : undefined}>
                <td>{r.cls.replace(/_/g, ' ')}</td><td>{r.hs}</td><td>{r.cond}</td><td className="mono">{r.action}</td><td>{r.result}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="hint">Thresholds (deviation %, number of cycles) are configurable in Settings. A hotspot alert suppresses the automatic cleaning / tilt; the operator can still run either manually.</p>
    </div>
  )
}
