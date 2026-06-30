import { useState } from 'react'

function buildTicks() {
  const ticks = []
  for (let h = 7; h <= 21; h++) {
    ticks.push({ label: `${String(h).padStart(2,'0')}:00`, minute: 0, hour: h })
    if (h < 21) ticks.push({ label: `${String(h).padStart(2,'0')}:30`, minute: 30, hour: h })
  }
  return ticks
}
const TICKS = buildTicks()

export default function TimeControl({ selectedTime, onChange, lang = 'it' }) {
  const [custom, setCustom] = useState(false)

  function applyOffset(offsetHours) {
    const d = new Date()
    d.setHours(d.getHours() + offsetHours, 0, 0, 0)
    // Clamp to 07:00-21:00
    if (d.getHours() < 7) d.setHours(7)
    if (d.getHours() > 21) d.setHours(21)
    onChange(d.toISOString())
  }

  const pillStyle = (active) => ({
    padding: '5px 12px', borderRadius: 16, fontSize: 12, fontWeight: 500,
    border: `1.5px solid ${active ? 'var(--route-shade)' : 'var(--border)'}`,
    background: active ? 'var(--route-shade)' : '#fff',
    color: active ? '#fff' : 'var(--text-primary)',
    cursor: 'pointer',
  })

  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6, fontWeight: 600, letterSpacing: '0.05em' }}>
        TIME CONTROL
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <button style={pillStyle(!selectedTime && !custom)}
          onClick={() => { setCustom(false); onChange(null) }}>
          Adesso
        </button>
        <button style={pillStyle(false)} onClick={() => applyOffset(1)}>+1h</button>
        <button style={pillStyle(false)} onClick={() => applyOffset(2)}>+2h</button>
        <button style={pillStyle(custom)}
          onClick={() => setCustom(c => !c)}>
          Personalizza
        </button>
      </div>
      {custom && (
        <select
          style={{ marginTop: 8, padding: '6px 10px', borderRadius: 8,
                   border: '1.5px solid var(--border)', fontSize: 13, width: '100%' }}
          onChange={e => {
            const tick = TICKS[parseInt(e.target.value)]
            const d = new Date()
            d.setHours(tick.hour, tick.minute, 0, 0)
            onChange(d.toISOString())
          }}>
          {TICKS.map((t, i) => <option key={i} value={i}>{t.label}</option>)}
        </select>
      )}
    </div>
  )
}
