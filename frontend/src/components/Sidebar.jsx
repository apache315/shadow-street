import RouteCard from './RouteCard.jsx'
import TimeControl from './TimeControl.jsx'

const I18N = {
  it: { title: 'Pisa — percorsi ombrosi', popularPlaces: 'LUOGHI POPOLARI', calculatingRoutes: 'Calcolo percorsi…', nightMessage: 'Di notte tutti i percorsi sono in ombra — mostriamo il più breve.' },
  en: { title: 'Pisa — shaded routes', popularPlaces: 'POPULAR PLACES', calculatingRoutes: 'Calculating routes…', nightMessage: 'At night all routes are shaded — showing the shortest one.' },
}

const PISA_LANDMARKS = [
  'Torre di Pisa', 'Piazza dei Miracoli', 'Università di Pisa',
  'Stazione Pisa Centrale', 'Piazza dei Cavalieri',
]

export default function Sidebar({
  fastest, shadiest, night, activeRoute, onSelectRoute,
  selectedTime, onTimeChange, lang = 'it', loading, onLandmarkClick,
}) {
  const t = I18N[lang]
  return (
    <div style={{
      position: 'absolute', top: 0, left: 0, bottom: 0,
      width: 320, background: '#fff', zIndex: 20,
      boxShadow: '2px 0 16px rgba(0,0,0,0.1)',
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{ padding: '20px 16px 12px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontWeight: 700, fontSize: 18, marginBottom: 4 }}>🌿 Shadow Street</div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{t.title}</div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
        {/* Landmarks (shown before search) */}
        {!fastest && !loading && (
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)',
                          letterSpacing: '0.05em', marginBottom: 8 }}>{t.popularPlaces}</div>
            {PISA_LANDMARKS.map((name, i) => (
              <div key={i}
                onClick={() => onLandmarkClick?.(name)}
                style={{ padding: '10px 0', fontSize: 13, cursor: 'pointer',
                         borderBottom: '1px solid var(--border)',
                         color: 'var(--text-primary)' }}>
                📍 {name}
              </div>
            ))}
          </div>
        )}

        {loading && (
          <div style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: 24 }}>
            {t.calculatingRoutes}
          </div>
        )}

        {night && fastest && (
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', padding: '8px 0' }}>
            {t.nightMessage}
          </div>
        )}

        {fastest && shadiest && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 8 }}>
            <RouteCard type="fastest" info={fastest} lang={lang}
              active={activeRoute === 'fastest'}
              onClick={() => onSelectRoute('fastest')} />
            <RouteCard type="shadiest" info={shadiest} lang={lang}
              active={activeRoute === 'shadiest'}
              onClick={() => onSelectRoute('shadiest')} />
          </div>
        )}

        {(fastest || shadiest) && (
          <TimeControl lang={lang} selectedTime={selectedTime} onChange={onTimeChange} />
        )}
      </div>
    </div>
  )
}
