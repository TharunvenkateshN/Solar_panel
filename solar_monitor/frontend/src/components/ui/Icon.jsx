const P = {
  overview: <><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></>,
  scenarios: <><path d="M4 6h9M19 6h1M4 12h3M11 12h9M4 18h11M19 18h1" /><circle cx="16" cy="6" r="2" /><circle cx="9" cy="12" r="2" /><circle cx="17" cy="18" r="2" /></>,
  panel: <><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" /><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5" /></>,
  thermal: <path d="M10 14.5V5a2 2 0 114 0v9.5a4 4 0 11-4 0z" />,
  workflow: <><circle cx="6" cy="6" r="2.4" /><circle cx="6" cy="18" r="2.4" /><circle cx="18" cy="12" r="2.4" /><path d="M6 8.4v7.2M8.4 6H12a3 3 0 013 3v.6M8.4 18H12a3 3 0 003-3v-.6" /></>,
  analytics: <><path d="M4 20V4M4 20h16" /><path d="M8 15l4-4 3 3 5-6" /></>,
  events: <><path d="M6 9a6 6 0 1112 0c0 5 2 6 2 6H4s2-1 2-6z" /><path d="M10 19a2 2 0 004 0" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" /></>,
  about: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7.5v.01" /></>,
  play: <path d="M7 4.5v15l12-7.5z" fill="currentColor" stroke="none" />,
  pause: <><rect x="6" y="4.5" width="4" height="15" rx="1" fill="currentColor" stroke="none" /><rect x="14" y="4.5" width="4" height="15" rx="1" fill="currentColor" stroke="none" /></>,
  step: <><path d="M5 5v14l9-7z" fill="currentColor" stroke="none" /><path d="M18 5v14" /></>,
  reset: <><path d="M4 12a8 8 0 108-8H8" /><path d="M8 1l-4 3 4 3" /></>,
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5" /></>,
  broom: <><path d="M14 4l6 6M12.5 8.5l3 3" /><path d="M13 11c-3 0-7 2-8 9h9c.7-3 .8-6-1-9z" /></>,
  tilt: <><path d="M4 18l12-6" /><path d="M4 18h16" /><path d="M12 18a8 8 0 00-1.5-4.6" /></>,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  cloud: <path d="M7 18a4 4 0 01-.6-7.95A5.5 5.5 0 0117 9.5a4.25 4.25 0 01.5 8.5z" />,
  rain: <><path d="M7 14a4 4 0 01-.6-7.95A5.5 5.5 0 0117 5.5a4.25 4.25 0 01.5 8.5z" /><path d="M8 17l-1 3M12 17l-1 3M16 17l-1 3" /></>,
  dust: <><path d="M3 8h11a2.5 2.5 0 10-2.5-2.5" /><path d="M3 12h16a2.5 2.5 0 11-2.5 2.5" /><path d="M3 16h8a2 2 0 11-2 2" /></>,
  heat: <><path d="M10 13.5V5a2 2 0 114 0v8.5a4 4 0 11-4 0z" /><path d="M18 5c1 1 1 2 0 3M21 4c1.2 1.4 1.2 3 0 4.4" /></>,
  sunrise: <><path d="M3 18h18M7 18a5 5 0 0110 0" /><path d="M12 5v3M4.5 10l1.8 1.5M19.5 10l-1.8 1.5" /></>,
  dusk: <><path d="M3 18h18M7 18a5 5 0 0110 0" /><path d="M12 12v-1M5 13l-1-1M19 13l1-1" /></>,
  moon: <path d="M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z" />,
  shadow: <><rect x="4" y="5" width="16" height="14" rx="2" /><path d="M12 5v14M16 5v14M20 5v14" /></>,
  shadow_off: <><rect x="4" y="5" width="16" height="14" rx="2" /><path d="M9 12l2 2 4-4" /></>,
  flame: <path d="M12 3c1 3 5 5 5 10a5 5 0 01-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-6 1-9z" />,
  wrench: <path d="M14.5 6.5a4 4 0 00-5 5L4 17l3 3 5.5-5.5a4 4 0 005-5L15 12l-3-3z" />,
  flat: <><path d="M3 14h18" /><path d="M6 14l3-3M18 14l-3-3" /></>,
  check: <path d="M5 12l5 5 9-10" />,
  spark: <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />,
}

export default function Icon({ name, size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {P[name]}
    </svg>
  )
}
