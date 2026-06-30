import { useRef, useState } from 'react'
import Map from './components/Map.jsx'
import SearchBar from './components/SearchBar.jsx'
import RouteLayer from './components/RouteLayer.jsx'
import BottomSheet from './components/BottomSheet.jsx'
import Sidebar from './components/Sidebar.jsx'
import { useGeolocation } from './hooks/useGeolocation.js'
import { useRoutes } from './hooks/useRoutes.js'

export default function App() {
  const [lang, setLang] = useState('it')
  const [destination, setDestination] = useState(null)
  const [selectedTime, setSelectedTime] = useState(null)
  const [activeRoute, setActiveRoute] = useState('shadiest')
  const mapRef = useRef(null)
  const { position } = useGeolocation()
  const start = position  // GPS position as start
  const { fastest, shadiest, loading, error, night } = useRoutes(start, destination, selectedTime)
  const isDesktop = window.innerWidth >= 768

  function handleGPS() {
    if (position && mapRef.current) {
      mapRef.current.flyTo({ center: [position.lng, position.lat], zoom: 16 })
    }
  }

  return (
    <div style={{ position: 'relative', width: '100%', height: '100dvh' }}>
      {isDesktop && (
        <Sidebar
          fastest={fastest} shadiest={shadiest} night={night}
          activeRoute={activeRoute} onSelectRoute={setActiveRoute}
          selectedTime={selectedTime} onTimeChange={setSelectedTime}
          lang={lang} loading={loading}
        />
      )}

      <div style={{
        position: 'absolute',
        left: isDesktop ? 320 : 0,
        top: 0, right: 0, bottom: 0,
      }}>
        <Map onMapReady={m => { mapRef.current = m }} />

        {mapRef.current && fastest && (
          <RouteLayer map={mapRef.current} routeId="fastest"
            geojson={fastest.geojson} color="#FF8C00" />
        )}
        {mapRef.current && shadiest && (
          <RouteLayer map={mapRef.current} routeId="shadiest"
            geojson={shadiest.geojson} color="#1565C0" />
        )}

        <div style={{
          position: 'absolute', top: 16, right: 12, zIndex: 10,
          background: '#fff', borderRadius: 20, padding: '4px 10px',
          boxShadow: 'var(--shadow-sm)', fontSize: 12, fontWeight: 600,
          cursor: 'pointer',
        }} onClick={() => setLang(l => l === 'it' ? 'en' : 'it')}>
          {lang.toUpperCase()}
        </div>

        <SearchBar lang={lang} onSelect={setDestination} />

        <button onClick={handleGPS} style={{
          position: 'absolute', bottom: 140, right: 16, zIndex: 10,
          width: 48, height: 48, borderRadius: '50%',
          background: 'var(--route-shade)', border: 'none',
          boxShadow: 'var(--shadow-md)', cursor: 'pointer',
          fontSize: 20, color: '#fff', display: 'flex',
          alignItems: 'center', justifyContent: 'center',
        }}>📍</button>

        {loading && (
          <div style={{
            position: 'absolute', top: 70, left: '50%', transform: 'translateX(-50%)',
            background: '#fff', borderRadius: 20, padding: '6px 16px',
            boxShadow: 'var(--shadow-sm)', fontSize: 13, zIndex: 10,
          }}>Calcolo percorsi…</div>
        )}
      </div>

      {!isDesktop && (
        <BottomSheet
          fastest={fastest}
          shadiest={shadiest}
          night={night}
          activeRoute={activeRoute}
          onSelectRoute={setActiveRoute}
          selectedTime={selectedTime}
          onTimeChange={setSelectedTime}
          lang={lang}
          loading={loading}
        />
      )}
    </div>
  )
}
