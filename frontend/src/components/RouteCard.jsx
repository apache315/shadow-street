const I18N = {
  it: { fastest: 'Più veloce', shadiest: 'Più ombra', recommended: 'CONSIGLIATO', min: 'min' },
  en: { fastest: 'Fastest', shadiest: 'Shadiest', recommended: 'RECOMMENDED', min: 'min' },
}

export default function RouteCard({ type, info, active, onClick, lang = 'it' }) {
  if (!info) return null
  const t = I18N[lang]
  const color = type === 'fastest' ? 'var(--route-fast)' : 'var(--route-shade)'
  const icon = type === 'fastest' ? '☀️' : '🌿'
  const label = type === 'fastest' ? t.fastest : t.shadiest
  const isRecommendedMonth = new Date().getMonth() >= 5 && new Date().getMonth() <= 8
  const showBadge = type === 'shadiest' && isRecommendedMonth

  return (
    <div onClick={onClick} style={{
      flex: 1, background: active ? `${color}18` : '#fff',
      border: `2px solid ${active ? color : 'var(--border)'}`,
      borderRadius: 'var(--radius-sm)', padding: '12px',
      cursor: 'pointer', transition: 'all 0.15s', position: 'relative',
    }}>
      {showBadge && (
        <div style={{
          position: 'absolute', top: -10, left: '50%', transform: 'translateX(-50%)',
          background: 'var(--green-badge)', color: '#fff', fontSize: 9,
          fontWeight: 700, padding: '2px 8px', borderRadius: 10, whiteSpace: 'nowrap',
        }}>{t.recommended}</div>
      )}
      <div style={{ color, fontWeight: 600, fontSize: 13, marginBottom: 6 }}>
        {icon} {label}
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
        <div>⏱ {Math.round(info.total_duration_s / 60)} {t.min}</div>
        <div>→ {Math.round(info.total_distance_m)}m</div>
        <div>🌿 {info.shade_pct}% ombra</div>
      </div>
    </div>
  )
}
