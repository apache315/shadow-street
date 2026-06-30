import { useEffect } from 'react'

export default function RouteLayer({ map, routeId, geojson, color }) {
  useEffect(() => {
    if (!map || !geojson) return
    const sourceId = `route-${routeId}`
    const layerId = `route-layer-${routeId}`

    if (map.getSource(sourceId)) {
      map.getSource(sourceId).setData(geojson)
    } else {
      map.addSource(sourceId, { type: 'geojson', data: geojson })
      map.addLayer({
        id: layerId,
        type: 'line',
        source: sourceId,
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: {
          'line-color': color,
          'line-width': 5,
          'line-opacity': 0.85,
        },
      })
    }
    return () => {
      if (map.getLayer(layerId)) map.removeLayer(layerId)
      if (map.getSource(sourceId)) map.removeSource(sourceId)
    }
  }, [map, geojson, color, routeId])

  return null
}
