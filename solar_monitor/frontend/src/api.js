// Empty (default) = same origin as the page (local run / Render). Set VITE_BACKEND_URL when the frontend is
// hosted separately (e.g. Vercel) and the backend lives elsewhere (e.g. Render).
export const BACKEND = (import.meta.env.VITE_BACKEND_URL || '').replace(/\/+$/, '')

async function call(method, url, body) {
  const res = await fetch(BACKEND + url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  let data = null
  try { data = await res.json() } catch { /* empty body */ }
  if (!res.ok) throw new Error(data?.detail || `${method} ${url} failed (${res.status})`)
  return data
}

export const api = {
  scenario: (id) => call('POST', `/api/scenario/${id}`),
  params: (changes) => call('PUT', '/api/params', changes),
  config: (changes) => call('PUT', '/api/config', changes),
  sim: (op) => call('POST', `/api/sim/${op}`),
  command: (action) => call('POST', `/api/command/${action}`),
  event: (id, params) => call('POST', `/api/event/${id}`, params ? { params } : { params: {} }),
  reloadClassifier: () => call('POST', '/api/classifier/reload'),
}
