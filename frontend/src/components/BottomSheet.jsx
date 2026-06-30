import { useState, useRef } from 'react'
import RouteCard from './RouteCard.jsx'
import TimeControl from './TimeControl.jsx'

const I18N = {
  it: { calculating: 'Calcolo…', routesFound: '2 percorsi trovati ↑', searchPrompt: 'Cerca una destinazione', nightMessage: 'Di notte tutti i percorsi sono in ombra — mostriamo il più breve.' },
  en: { calculating: 'Calculating…', routesFound: '2 routes found ↑', searchPrompt: 'Search for a destination', nightMessage: 'At night all routes are shaded — showing the shortest one.' },
}

export default function BottomSheet({
  fastest, shadiest, night, activeRoute, onSelectRoute, selectedTime, onTimeChange,
  lang = 'it', loading,
}) {
  const [sheetState, setSheetState] = useState('collapsed') // collapsed|mid|expanded
  const startY = useRef(null)
  const t = I18N[lang]

  const heights = { collapsed: 80, mid: '50vh', expanded: '90vh' }

  function handleTouchStart(e) { startY.current = e.touches[0].clientY }
  function handleTouchEnd(e) {
    const dy = startY.current - e.changedTouches[0].clientY
    if (dy > 40) setSheetState(s => s === 'collapsed' ? 'mid' : 'expanded')
    if (dy < -40) setSheetState(s => s === 'expanded' ? 'mid' : 'collapsed')
  }

  const hasRoutes = fastest && shadiest

  return (
    <div
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
      style={{
        position: 'absolute', bottom: 0, left: 0, right: 0,
        background: '#fff', borderRadius: '20px 20px 0 0',
        boxShadow: '0 -4px 24px rgba(0,0,0,0.15)',
        height: typeof heights[sheetState] === 'number'
          ? `${heights[sheetState]}px` : heights[sheetState],
        transition: 'height 0.3s cubic-bezier(0.4,0,0.2,1)',
        zIndex: 20, padding: '0 16px 24px', overflow: 'hidden',
      }}>

      {/* Handle */}
      <div onClick={() => setSheetState(s => s === 'collapsed' ? 'mid' : s === 'mid' ? 'expanded' : 'collapsed')}
        style={{ padding: '10px 0 8px', display: 'flex', justifyContent: 'center', cursor: 'pointer' }}>
        <div style={{ width: 36, height: 4, background: '#ddd', borderRadius: 2 }} />
      </div>

      {/* Hint when collapsed */}
      {sheetState === 'collapsed' && (
        <div style={{ textAlign: 'center', fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
          {loading ? t.calculating : hasRoutes ? t.routesFound : t.searchPrompt}
        </div>
      )}

      {/* Night message */}
      {sheetState !== 'collapsed' && night && (
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', textAlign: 'center', padding: '8px 0' }}>
          {t.nightMessage}
        </div>
      )}

      {/* Route cards */}
      {sheetState !== 'collapsed' && hasRoutes && (
        <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
          <RouteCard type="fastest" info={fastest} lang={lang}
            active={activeRoute === 'fastest'}
            onClick={() => onSelectRoute('fastest')} />
          <RouteCard type="shadiest" info={shadiest} lang={lang}
            active={activeRoute === 'shadiest'}
            onClick={() => onSelectRoute('shadiest')} />
        </div>
      )}

      {/* Time control */}
      {sheetState !== 'collapsed' && (
        <TimeControl lang={lang} selectedTime={selectedTime} onChange={onTimeChange} />
      )}
    </div>
  )
}
