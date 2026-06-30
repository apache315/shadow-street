import { useState, useEffect } from 'react'
import { fetchRoutes } from '../api.js'

export function useRoutes(start, end, selectedTime) {
  const [fastest, setFastest] = useState(null)
  const [shadiest, setShadiest] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [night, setNight] = useState(false)

  useEffect(() => {
    if (!start || !end) return
    setLoading(true)
    setError(null)
    fetchRoutes(start, end, selectedTime)
      .then(data => {
        setFastest(data.fastest)
        setShadiest(data.shadiest)
        setNight(data.night)
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [start?.lat, start?.lng, end?.lat, end?.lng, selectedTime])

  return { fastest, shadiest, loading, error, night }
}
