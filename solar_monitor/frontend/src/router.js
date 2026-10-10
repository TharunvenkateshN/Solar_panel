import { useEffect, useState } from 'react'

export const ROUTES = [
  { id: 'overview', label: 'Overview', hint: 'Status, readings and live 3D panel' },
  { id: 'scenarios', label: 'Scenarios & controls', hint: 'Pick a scenario, change sensor inputs' },
  { id: 'panel', label: '3D panel & actions', hint: 'Cleaning and tilting in 3D, before / after' },
  { id: 'thermal', label: 'Thermal & sensors', hint: '8×8 thermal grid, hotspot rules, I-V curve' },
  { id: 'workflow', label: 'Workflow', hint: 'Every pipeline stage and the decision rules' },
  { id: 'analytics', label: 'Analytics', hint: 'Charts and trends (simulated history)' },
  { id: 'events', label: 'Events & MQTT', hint: 'Event history and message monitor' },
  { id: 'settings', label: 'Settings', hint: 'Thresholds, actuators, classifier, MQTT' },
  { id: 'about', label: 'About', hint: 'Implemented vs simulated vs pending' },
]

const read = () => {
  const id = location.hash.replace(/^#\/?/, '') || 'overview'
  return ROUTES.some((r) => r.id === id) ? id : 'overview'
}

export function useRoute() {
  const [route, setRoute] = useState(read)
  useEffect(() => {
    const on = () => { setRoute(read()); window.scrollTo({ top: 0 }) }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return [route, (id) => { location.hash = `#/${id}` }]
}
