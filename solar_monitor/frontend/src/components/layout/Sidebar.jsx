import { ROUTES } from '../../router.js'
import Icon from '../ui/Icon.jsx'

export default function Sidebar({ route, go, open, onClose, badges }) {
  return (
    <>
      <div className={`scrim ${open ? 'show' : ''}`} onClick={onClose} aria-hidden="true" />
      <nav id="main-nav" className={`sidebar ${open ? 'open' : ''}`} aria-label="Main navigation">
        <div className="side-brand">
          <span className="logo" aria-hidden="true"><Icon name="sun" size={22} /></span>
          <div><strong>Solar Monitor</strong><small>Simulation</small></div>
          <button className="icon-btn close" onClick={onClose} aria-label="Close navigation"><Icon name="close" size={18} /></button>
        </div>
        <ul>
          {ROUTES.map((r) => (
            <li key={r.id}>
              <a href={`#/${r.id}`} className={route === r.id ? 'active' : ''} aria-current={route === r.id ? 'page' : undefined}
                onClick={(e) => { e.preventDefault(); go(r.id); onClose() }} title={r.hint}>
                <Icon name={r.id === 'panel' ? 'panel' : r.id} />
                <span>{r.label}</span>
                {badges[r.id] && <span className={`nav-badge ${badges[r.id].tone}`}>{badges[r.id].text}</span>}
              </a>
            </li>
          ))}
        </ul>
        <p className="side-foot">All sensor values are simulated. No hardware is connected.</p>
      </nav>
    </>
  )
}
