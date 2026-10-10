import { useState } from 'react'
import { useSim } from './useSim.js'
import { useRoute } from './router.js'
import { actionBusy } from './format.js'
import Sidebar from './components/layout/Sidebar.jsx'
import Topbar from './components/layout/Topbar.jsx'
import ActionBar from './components/layout/ActionBar.jsx'
import { AboutView, AnalyticsView, EventsView, OverviewView, PanelView, ScenariosView, SettingsView, ThermalView, WorkflowView } from './components/views/Views.jsx'

const VIEWS = {
  overview: OverviewView, scenarios: ScenariosView, panel: PanelView, thermal: ThermalView,
  workflow: WorkflowView, analytics: AnalyticsView, events: EventsView, settings: SettingsView, about: AboutView,
}

export default function App() {
  const s = useSim()
  const [route, go] = useRoute()
  const [menu, setMenu] = useState(false)
  const View = VIEWS[route]

  const hs = s.result?.thermal?.hotspot_detected === 'YES'
  const badges = {}
  if (hs) badges.thermal = { tone: 'alert', text: 'ALERT' }
  if (actionBusy(s.action)) badges.panel = { tone: 'info', text: 'LIVE' }

  return (
    <div className="app">
      <a className="skip" href="#content">Skip to content</a>
      <Sidebar route={route} go={go} open={menu} onClose={() => setMenu(false)} badges={badges} />
      <div className="shell">
        {s.loaded && <Topbar s={s} onMenu={() => setMenu(true)} />}
        {s.loaded && <ActionBar s={s} route={route} go={go} />}
        <main id="content" className="content" tabIndex={-1}>
          {!s.loaded ? (
            <p className="loading">{s.connected ? 'Loading…' : 'Connecting to the simulation backend… (is `python run.py` running?)'}</p>
          ) : <View s={s} go={go} />}
        </main>
      </div>
    </div>
  )
}
