const BASE = '/api'

export async function fetchRoutes(start, end, datetime = null) {
  const body = { start: [start.lat, start.lng], end: [end.lat, end.lng] }
  if (datetime) body.datetime = datetime
  const res = await fetch(`${BASE}/route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`API error ${res.status}`)
  return res.json()
}
