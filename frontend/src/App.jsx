import { useRef, useState } from 'react'
import Map from './components/Map.jsx'

export default function App() {
  const [mapReady, setMapReady] = useState(false)

  return (
    <div style={{ position: 'relative', width: '100%', height: '100dvh' }}>
      <Map onMapReady={() => setMapReady(true)} />
    </div>
  )
}
