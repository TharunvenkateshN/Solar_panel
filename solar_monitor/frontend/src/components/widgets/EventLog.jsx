import { useState } from 'react'
import { simClockSec, wallClock } from '../../format.js'

const FILTERS = {
  All: () => true,
  Alerts: (e) => e.level === 'alert' || e.level === 'error',
  Actions: (e) => ['COMMAND', 'ACTION', 'VERIFY', 'DECISION'].includes(e.type),
  System: (e) => e.origin === 'runtime',
}

export default function EventLog({ s, limit = 120, maxHeight = 420, compact = false }) {
  const [filter, setFilter] = useState('All')
  const rows = s.events.filter(FILTERS[filter]).slice(-limit).reverse()
  return (
    <div>
      {!compact && (
        <div className="seg" role="group" aria-label="Filter events">
          {Object.keys(FILTERS).map((k) => (
            <button key={k} className={filter === k ? 'on' : ''} aria-pressed={filter === k} onClick={() => setFilter(k)}>{k}</button>
          ))}
        </div>
      )}
      <ul className="log" style={{ maxHeight }}>
        {rows.length === 0 && <li className="empty">No events.</li>}
        {rows.map((e) => (
          <li key={e.id} className={`log-row ${e.level}`}>
            <span className="t" title={`wall clock ${wallClock(e.wall_time)}`}>{simClockSec(e.sim_time)}</span>
            <span className="msg"><b>{e.type}</b> {e.message}</span>
            <span className={`pill ${e.origin === 'runtime' ? 'rt' : 'sim'}`}
              title={e.origin === 'runtime' ? 'Real software / operator event on this machine' : 'Derived from simulated sensor data'}>
              {e.origin === 'runtime' ? 'RUNTIME' : 'SIM'}
            </span>
          </li>
        ))}
      </ul>
      {!compact && <p className="hint">Times are the simulation clock (hover for wall clock). SIM = derived from simulated data; RUNTIME = real software or operator events (configuration, MQTT connection, errors).</p>}
    </div>
  )
}
