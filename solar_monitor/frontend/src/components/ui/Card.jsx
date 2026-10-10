export function Card({ title, sim, rt, actions, children, className = '', id }) {
  return (
    <section className={`card ${className}`} id={id} aria-labelledby={title ? `${id || title}-h` : undefined}>
      {(title || actions) && (
        <header className="card-head">
          {title && <h2 id={`${id || title}-h`}>{title}{sim && <span className="pill sim">SIMULATED</span>}{rt && <span className="pill rt">RUNTIME</span>}</h2>}
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  )
}

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {children && <div className="page-head-actions">{children}</div>}
    </div>
  )
}

export const Pill = ({ tone = '', children, title }) => <span className={`pill ${tone}`} title={title}>{children}</span>
