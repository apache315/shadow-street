import { useRef, useState } from 'react'
import Map from './components/Map.jsx'
import SearchBar from './components/SearchBar.jsx'
import { useGeolocation } from './hooks/useGeolocation.js'

export default function App() {
  const [lang, setLang] = useState('it')
  const [destination, setDestination] = useState(null)
  const mapRef = useRef(null)
  const { position } = useGeolocation()

  function handleGPS() {
    if (position && mapRef.current) {
      mapRef.current.flyTo({ center: [position.lng, position.lat], zoom: 16 })
    }
  }

  return (
    <div style={{ position: 'relative', width: '100%', height: '100dvh' }}>
      <Map onMapReady={m => { mapRef.current = m }} />

      {/* Language toggle */}
      <div style={{
        position: 'absolute', top: 16, right: 12, zIndex: 10,
        background: '#fff', borderRadius: 20, padding: '4px 10px',
        boxShadow: 'var(--shadow-sm)', fontSize: 12, fontWeight: 600,
        cursor: 'pointer', userSelect: 'none',
      }} onClick={() => setLang(l => l === 'it' ? 'en' : 'it')}>
        {lang.toUpperCase()}
      </div>

      <SearchBar lang={lang} onSelect={setDestination} />

      {/* GPS FAB */}
      <button onClick={handleGPS} style={{
        position: 'absolute', bottom: 140, right: 16, zIndex: 10,
        width: 48, height: 48, borderRadius: '50%',
        background: 'var(--route-shade)', border: 'none',
        boxShadow: 'var(--shadow-md)', cursor: 'pointer',
        fontSize: 20, color: '#fff', display: 'flex',
        alignItems: 'center', justifyContent: 'center',
      }}>
        📍
      </button>
    </div>
  )
}
