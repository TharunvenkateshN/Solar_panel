import { useEffect, useReducer } from 'react'

const initial = {
  connected: false, loaded: false, scenarios: [], scenarioId: 'healthy', scenarioLabel: '',
  params: {}, truth: null, config: {}, sim: {}, result: null, stages: [], history: [],
  events: [], messages: [], action: null, verification: null, classifier: null, mqtt: null, catalog: [],
}

const cap = (arr, n) => (arr.length > n ? arr.slice(arr.length - n) : arr)

function reducer(s, a) {
  if (a.type === 'conn') return { ...s, connected: a.v }
  const m = a.m
  switch (m.type) {
    case 'snapshot':
      return { ...s, loaded: true, scenarios: m.scenarios, scenarioId: m.scenario_id, scenarioLabel: m.scenario_label,
        params: m.params, truth: m.truth, config: m.config, sim: m.sim, result: m.result,
        stages: m.result?.stages || [], history: m.history, events: m.events, messages: m.messages,
        action: m.action, verification: m.verification, classifier: m.classifier, mqtt: m.mqtt, catalog: m.event_catalog || [] }
    case 'tick':
      return { ...s, result: m.result, stages: m.result.stages, truth: m.truth, sim: m.sim,
        history: cap([...s.history, m.history_point], 400) }
    case 'truth': return { ...s, truth: m.truth }
    case 'stages': return { ...s, stages: m.stages }
    case 'action': return { ...s, action: m.action }
    case 'verification': return { ...s, verification: m.verification }
    case 'event': return { ...s, events: cap([...s.events, m.event], 500) }
    case 'bus': return { ...s, messages: cap([...s.messages, m.message], 80) }
    case 'scenario':
      return { ...s, scenarioId: m.scenario_id, scenarioLabel: m.scenario_label, params: m.params, truth: m.truth }
    case 'config': return { ...s, config: m.config }
    case 'sim': return { ...s, sim: m.sim }
    case 'mqtt': return { ...s, mqtt: m.mqtt }
    case 'classifier': return { ...s, classifier: m.classifier }
    default: return s
  }
}

export function useSim() {
  const [state, dispatch] = useReducer(reducer, initial)
  useEffect(() => {
    let ws, timer, closed = false
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws`)
      ws.onopen = () => dispatch({ type: 'conn', v: true })
      ws.onmessage = (e) => dispatch({ type: 'msg', m: JSON.parse(e.data) })
      ws.onclose = () => {
        dispatch({ type: 'conn', v: false })
        if (!closed) timer = setTimeout(connect, 1500)
      }
      ws.onerror = () => ws.close()
    }
    connect()
    return () => { closed = true; clearTimeout(timer); ws && ws.close() }
  }, [])
  return state
}
