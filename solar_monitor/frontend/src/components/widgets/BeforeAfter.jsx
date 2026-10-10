import { Bar, BarChart, CartesianGrid, Cell, LabelList, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import { f } from '../../format.js'

export default function BeforeAfter({ s }) {
  const v = s.verification
  const pv = s.stages?.find((x) => x.id === 'verification')
  if (!v) {
    return <p className="empty">{pv?.state === 'active' ? pv.headline : 'No corrective action has completed yet. Run a soiling or shading scenario, or start an action manually.'}</p>
  }
  const ok = v.verdict === 'RECOVERED' || v.verdict === 'NO_CHANGE'
  const noChange = v.verdict === 'NO_CHANGE'
  const data = [
    { name: 'Before', power: v.pre.power, fill: '#d98a00' },
    { name: 'After', power: v.post.power, fill: ok ? '#0b8f5a' : '#c62828' },
  ]
  return (
    <div className="ba">
      <div className="ba-chart">
        <ResponsiveContainer width="100%" height={210}>
          <BarChart data={data} margin={{ top: 22, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
            <XAxis dataKey="name" stroke="var(--muted)" />
            <YAxis stroke="var(--muted)" unit=" W" domain={[0, Math.ceil((v.post.expected || 30) * 1.2)]} width={52} />
            <ReferenceLine y={v.post.expected} stroke="var(--info)" strokeDasharray="4 4" label={{ value: 'expected', fill: 'var(--info)', fontSize: 11, position: 'insideTopRight' }} />
            <Bar dataKey="power" isAnimationActive={false} maxBarSize={90}>
              {data.map((d) => <Cell key={d.name} fill={d.fill} />)}
              <LabelList dataKey="power" position="top" formatter={(x) => `${f(x, 2)} W`} fill="var(--text)" fontSize={12} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="ba-facts">
        <div className={`verdict ${ok ? 'ok' : 'alert'}`}>
          {noChange ? '✔ Already within limits - no recovery needed' : ok ? '✔ Performance recovered (simulated)' : v.verdict === 'INCONCLUSIVE' ? '? Inconclusive' : '✘ Not recovered'}
        </div>
        <dl className="facts">
          <div><dt>Power</dt><dd>{f(v.pre.power, 2)} → {f(v.post.power, 2)} W ({v.power_gain_pct > 0 ? '+' : ''}{f(v.power_gain_pct, 1)}%)</dd></div>
          <div><dt>Deviation</dt><dd>{f(v.pre.deviation, 1)}% → {f(v.post.deviation, 1)}%</dd></div>
          <div><dt>Health</dt><dd>{f(v.pre.health, 1)}% → {f(v.post.health, 1)}%</dd></div>
          <div><dt>Criterion</dt><dd>{v.criterion}</dd></div>
        </dl>
        <p className="hint">{v.simulation_note}</p>
      </div>
    </div>
  )
}
