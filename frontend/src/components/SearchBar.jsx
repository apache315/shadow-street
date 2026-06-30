import { useState, useRef, useEffect } from 'react'

const NOMINATIM = 'https://nominatim.openstreetmap.org/search'
const PISA_LANDMARKS = [
  { label: 'Torre di Pisa', lat: 43.7230, lng: 10.3966 },
  { label: 'Piazza dei Miracoli', lat: 43.7230, lng: 10.3966 },
  { label: 'Università di Pisa', lat: 43.7196, lng: 10.4054 },
  { label: 'Stazione Pisa Centrale', lat: 43.7089, lng: 10.3985 },
  { label: 'Piazza dei Cavalieri', lat: 43.7215, lng: 10.4024 },
]

const I18N = {
  it: { placeholder: 'Dove vuoi andare?' },
  en: { placeholder: 'Where are you going?' },
}

export default function SearchBar({ lang = 'it', onSelect }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const debounce = useRef(null)

  useEffect(() => {
    if (query.length < 3) {
      setResults(PISA_LANDMARKS.filter(l =>
        l.label.toLowerCase().includes(query.toLowerCase())
      ))
      return
    }
    clearTimeout(debounce.current)
    debounce.current = setTimeout(async () => {
      try {
        const url = `${NOMINATIM}?q=${encodeURIComponent(query + ' Pisa')}&format=json&limit=5&countrycodes=it`
        const res = await fetch(url, {
          headers: { 'User-Agent': 'shadow-street-pisa/1.0' }
        })
        const data = await res.json()
        setResults(data.map(d => ({
          label: d.display_name.split(',')[0],
          lat: parseFloat(d.lat),
          lng: parseFloat(d.lon),
        })))
      } catch {
        setResults([])
      }
    }, 350)
  }, [query])

  function handleSelect(item) {
    setQuery(item.label)
    setOpen(false)
    onSelect(item)
  }

  return (
    <div style={{
      position: 'absolute', top: 12, left: 12, right: 56,
      zIndex: 10,
    }}>
      <div style={{
        background: '#fff',
        borderRadius: 'var(--radius-pill)',
        boxShadow: 'var(--shadow-md)',
        display: 'flex', alignItems: 'center', padding: '10px 16px', gap: 8,
      }}>
        <span style={{ color: 'var(--text-secondary)', fontSize: 16 }}>🔍</span>
        <input
          value={query}
          onChange={e => { setQuery(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          placeholder={I18N[lang].placeholder}
          style={{
            border: 'none', outline: 'none', flex: 1,
            font: '16px var(--font)', color: 'var(--text-primary)',
          }}
        />
        {query && (
          <button
            onClick={() => { setQuery(''); setOpen(false) }}
            style={{ background: 'none', border: 'none', cursor: 'pointer',
                     color: 'var(--text-secondary)', fontSize: 18, lineHeight: 1 }}>
            ×
          </button>
        )}
      </div>
      {open && results.length > 0 && (
        <div style={{
          background: '#fff', borderRadius: 'var(--radius-sm)',
          boxShadow: 'var(--shadow-md)', marginTop: 4, overflow: 'hidden',
        }}>
          {results.map((r, i) => (
            <div key={i}
              onClick={() => handleSelect(r)}
              style={{
                padding: '12px 16px', cursor: 'pointer', fontSize: 14,
                borderBottom: i < results.length - 1 ? '1px solid var(--border)' : 'none',
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--surface)'}
              onMouseLeave={e => e.currentTarget.style.background = '#fff'}
            >
              {r.label}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
