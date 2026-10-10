import { api } from '../../api.js'
import { pretty } from '../../format.js'

export default function ScenarioPicker({ s, columns = true }) {
  return (
    <div className={columns ? 'scenario-grid' : 'scenario-list'} role="radiogroup" aria-label="Scenario">
      {s.scenarios.map((sc, i) => (
        <button key={sc.id} role="radio" aria-checked={sc.id === s.scenarioId}
          className={`scenario ${sc.id === s.scenarioId ? 'active' : ''}`} onClick={() => api.scenario(sc.id)}>
          <span className="num">{i + 1}</span>
          <span className="scenario-text">
            <strong>{sc.name}</strong>
            <small>{sc.description}</small>
            <em>Expect: {pretty(sc.expected)}</em>
          </span>
        </button>
      ))}
    </div>
  )
}
