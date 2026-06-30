import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'

const PISA_CENTER = [10.4017, 43.7228]
const MAP_STYLE = 'https://tiles.openfreemap.org/styles/liberty'

export default function Map({ onMapReady }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)

  useEffect(() => {
    if (mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: PISA_CENTER,
      zoom: 14,
    })
    map.addControl(new maplibregl.NavigationControl(), 'top-right')
    map.on('load', () => {
      mapRef.current = map
      onMapReady?.(map)
    })
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
}
