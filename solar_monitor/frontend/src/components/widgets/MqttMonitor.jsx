import { useState } from 'react'
import { f, wallClock } from '../../format.js'

const TOPICS = ['all', 'data', 'status', 'command', 'feedback']

function summary(topic, p) {
  if (topic.endsWith('/data')) return `${f(p.ina219?.voltage_V, 2)} V · ${f(p.ina219?.current_A, 3)} A · ${f(p.bh1750?.lux, 0)} lx · 8×8 grid`
  if (topic.endsWith('/status')) return `${p.ml_class} · hotspot ${p.hotspot} · ${p.final_status} → ${p.recommended_action}`
  if (topic.endsWith('/command')) return `${p.command} (${p.source}) ${p.command_id}`
  if (topic.endsWith('/feedback')) return `${p.actuator} ${p.state}${p.progress != null ? ` ${p.progress}%` : ''}${p.angle_deg != null ? ` @${f(p.angle_deg, 0)}°` : ''}`
  return ''
}

export default function MqttMonitor({ s, maxHeight = 420 }) {
  const [topic, setTopic] = useState('all')
  const [open, setOpen] = useState(null)
  const live = s.mqtt?.connected
  const rows = s.messages.filter((m) => topic === 'all' || m.topic === `solar/panel/${topic}`).slice(-40).reverse()
  return (
    <div>
      <p className={`note ${live ? 'good' : 'warn'}`}>
        {live ? `Broker ${s.mqtt.host}:${s.mqtt.port} connected - these messages went through the broker.`
          : `No broker connected (${s.mqtt?.last_error || 'not configured'}). Messages are delivered in-process ("local"), not over MQTT.`}
      </p>
      <div className="seg" role="group" aria-label="Filter topic">
        {TOPICS.map((t) => <button key={t} className={topic === t ? 'on' : ''} aria-pressed={topic === t} onClick={() => setTopic(t)}>{t === 'all' ? 'All topics' : t}</button>)}
      </div>
      <ul className="log mono" style={{ maxHeight }}>
        {rows.map((m, i) => {
          const key = m.wall_time + i
          return (
            <li key={key} className="msg-row">
              <button className="msg-btn" aria-expanded={open === key} onClick={() => setOpen(open === key ? null : key)}>
                <span className="msg-head">
                  <span className={`pill ${m.transport === 'mqtt' ? 'ok' : 'warn'}`}>{m.transport}</span>
                  <span className="topic">{m.topic}</span>
                  <span className="muted">{wallClock(m.wall_time)}</span>
                </span>
                <span className="msg-sum">{summary(m.topic, m.payload)}</span>
              </button>
              {open === key && <pre>{JSON.stringify(m.payload, null, 2)}</pre>}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
