# Shadow Street — Design Spec
**Date:** 2026-06-30  
**Status:** Approved  
**Scope:** Pisa-only MVP

---

## 1. Overview

Web app che calcola e mostra due percorsi a piedi nella città di Pisa:
- **Più veloce** — distanza/tempo minimo
- **Più ombra** — massima copertura ombra lungo il percorso

L'utente imposta la destinazione (e opzionalmente la partenza). L'app usa la posizione GPS come punto di partenza di default. I percorsi vengono calcolati in base all'ombra reale proiettata dagli edifici all'orario corrente, aggiornata ogni 30 minuti.

---

## 2. Target utenti

| Segmento | Comportamento | Priorità |
|----------|--------------|----------|
| Turisti Pisa | Uso occasionale, mobile, zero learning curve, cerca landmarks noti | Alta |
| Studenti Universitari | Uso quotidiano, velocità, familiari con Google Maps | Alta |
| Residenti | Uso ricorrente, preferenze personali | Media |

**Device:** Mobile-first (smartphone). Desktop supportato con layout sidebar.

---

## 3. Flusso principale

1. Utente apre app → mappa Pisa a schermo intero, bottom sheet collassato
2. Tap sulla search bar → inserisce destinazione (testo libero o landmark)
3. App usa GPS per posizione attuale (fallback: input manuale partenza)
4. Calcolo → 2 percorsi mostrati sulla mappa + nel bottom sheet
5. Utente può cambiare orario (default: ora attuale) → percorsi ricalcolati
6. Tap su percorso → seleziona, highlight sulla mappa, step-by-step opzionali

---

## 4. Architettura

```
┌─────────────────────────────────────────────────┐
│               FRONTEND                          │
│   React + MapLibre GL JS                        │
│   Mobile: full-screen map + bottom sheet        │
│   Desktop: sidebar 320px + mappa resto          │
│   Nominatim geocoding per search                │
└──────────────────┬──────────────────────────────┘
                   │ REST API (JSON)
┌──────────────────▼──────────────────────────────┐
│               BACKEND — FastAPI (Python)         │
│   POST /route  → {start, end, datetime}         │
│              → {fastest: GeoJSON, shadiest: GeoJSON} │
│   GET  /shadow-overlay → PNG tiles ombra attuale│
└──────────┬────────────────────┬─────────────────┘
           │                    │
┌──────────▼──────┐   ┌────────▼──────────────────┐
│  Shadow Cache   │   │   OSM Graph + Router       │
│  JSON su disco  │   │   osmnx (scarica Pisa)     │
│  aggiornato     │   │   networkx A* — UN grafo   │
│  ogni 30 min    │   │   fastest + shadiest       │
└──────────┬──────┘   └───────────────────────────┘
           │
┌──────────▼──────────────────────────────────────┐
│           Shadow Engine (cron, ogni 30 min)      │
│   pysolar  → posizione sole (alt, azimuth)      │
│   shapely  → proietta ombre edifici OSM          │
│   → % ombra per ogni segmento stradale          │
│   → salva weights in cache JSON                 │
└─────────────────────────────────────────────────┘
```

---

## 5. Componenti backend

### 5.1 Shadow Engine
- **Input:** datetime, bbox Pisa, edifici OSM (footprint + altezza stimata), alberi OSM
- **Altezza edifici:** tag `building:levels` × 3m. Dove assente: default 9m (3 piani, media centro storico Pisa). **Nota:** stima incerta, principale fonte di errore ombra.
- **Alberi (fonte ombra chiave per Pisa):** OSM `natural=tree` → chioma stimata come cerchio raggio 4m; `tree_row` → buffer lineare 4m. Importante per i Lungarni e viali alberati. Trattati come ombra parziale (shade_fraction 0.6 sotto chioma, l'ombra alberi non è opaca come edifici).
- **Librerie:** `pysolar` (posizione sole), `shapely` (geometrie ombra), `pyproj` (proiezione metrica UTM 32N)
- **Proiezione ombra:** `shadow_length = height / tan(sun_altitude)`, footprint esteso in direzione opposta all'azimuth solare.
- **Clamp sole basso:** se `sun_altitude < 10°` → ombre troppo lunghe/inaffidabili, fallback a "tutto ombra soft" (twilight). Se sole sotto orizzonte (notte) → engine ritorna shade=1.0 ovunque + flag `night=true`; il frontend mostra messaggio "Di notte tutti i percorsi sono in ombra — mostriamo il più breve".
- **Calcolo shade per arco:** campiona punti ogni ~5m lungo l'arco, point-in-polygon contro l'unione delle ombre (edifici + alberi) + portici fissi (`covered=yes` → shade=1.0). `shade_fraction` = frazione punti in ombra.
- **Output:** dizionario `{edge_id: shade_fraction}` (0.0 = pieno sole, 1.0 = ombra totale)
- **Cron:** ogni 30 minuti, 07:00–21:00 ora italiana
- **Storage:** file JSON nominato `shadows_HHMM.json`, rotazione giornaliera (dipende dal giorno dell'anno → ricalcolato ogni giorno)

### 5.2 Router
**Un solo grafo per entrambi i percorsi.** osmnx walk network di Pisa + networkx A*. No OSRM (incoerenza tra motori, snapping diverso, overkill per una città). Entrambi i percorsi sullo stesso grafo, cambia solo il peso.

- **Fastest route:** peso = `distance_m` puro.
- **Shadiest route:** peso che **penalizza i metri al sole** (non sconta l'ombra):
  ```
  sun_exposed_m = distance_m * (1 - shade_fraction)
  edge_cost     = distance_m + α * sun_exposed_m
  ```
  `α` = quanti metri extra l'utente accetta per evitare 1m di sole (tunabile, default α=2.0).
- **Cap deviazione:** se `shadiest_distance > 1.5 × fastest_distance` → scarta, rilassa α e ricalcola (o ritorna il fastest con nota "nessun percorso ombroso ragionevole"). Evita detour assurdi.
- **Annotazione shade:** ENTRAMBI i percorsi ricevono `shade_pct` per segmento dalla stessa cache (anche il fastest mostra la sua % ombra, come nel mockup).
- **Output:** GeoJSON FeatureCollection con proprietà per segmento: `{shade_pct, distance_m, duration_s}`

### 5.3 API Endpoints
```
POST /route
  Body: { start: [lat,lng], end: [lat,lng], datetime?: ISO8601 }
  Response: {
    fastest: { geojson, total_distance_m, total_duration_s, shade_pct },
    shadiest: { geojson, total_distance_m, total_duration_s, shade_pct }
  }

GET /health
  Response: { status: "ok", cache_age_minutes: int }
```

---

## 6. Componenti frontend

### 6.1 Layout Mobile
- **Mappa:** MapLibre GL JS, full-screen, stile light muted
- **Search bar:** flottante top, pill-shaped, shadow. Placeholder: "Dove vuoi andare? / Where are you going?"
- **Language toggle:** IT/EN top-right, minimal
- **FAB GPS:** bottom-right, 48dp, blu (#1565C0)
- **Bottom sheet:** 3 stati
  - Collassato (120px): drag handle + "2 percorsi trovati ↑"
  - Mid (50% schermo): 2 route card affiancate + time control
  - Expanded: dettaglio step-by-step + shade timeline

### 6.2 Layout Desktop
- **Sidebar sinistra:** 320px fixed
  - Search bar in header sidebar
  - Landmarks suggeriti (Torre di Pisa, Piazza dei Miracoli, ecc.)
  - Route cards verticali
  - Time control
- **Mappa:** resto dello schermo

### 6.3 Route Cards
```
Card "Più veloce" (orange #FF8C00):
  ☀️ Più veloce / Fastest
  ⏱ 8 min  →  650m  🌿 32% ombra

Card "Più ombra" (blue #1565C0):
  🌿 Più ombra / Shadiest        [CONSIGLIATO badge in estate]
  ⏱ 11 min  →  780m  🌿 73% ombra
```

### 6.4 Time Control
```
[Adesso]  [+1h]  [+2h]  [Personalizza]
Ora: 14:30 ☀️  ────●──────
```
**"Personalizza" limitato ai tick di OGGI** (07:00–21:00, step 30min) — solo orari presenti in cache. Niente date passate/future nel MVP (eviterebbe cache miss e calcolo on-demand lento). Date arbitrarie → v2.

### 6.5 Colori
| Token | Hex | Uso |
|-------|-----|-----|
| `--route-fast` | #FF8C00 | Percorso veloce |
| `--route-shade` | #1565C0 | Percorso ombroso |
| `--shade-overlay` | #B3C8F0 | Ombra su mappa (60% opacity) |
| `--text-primary` | #1A1A1A | Testo principale |
| `--text-secondary` | #757575 | Testo secondario |
| `--bg` | #FFFFFF | Background |
| `--green-badge` | #2E7D32 | Badge "CONSIGLIATO" |

### 6.6 Tipografia
- Font: **Inter** (Google Fonts, gratis, ottima leggibilità mobile)
- Scale: 12/14/16/20/24px

---

## 7. Dati e fonti

| Dato | Fonte | Note |
|------|-------|------|
| Edifici Pisa (footprint + altezza) | OpenStreetMap via `osmnx` | Altezza stimata dove mancante (default 9m) |
| Alberi e filari | OSM `natural=tree`, `tree_row` | Chioma stimata r=4m, ombra parziale 0.6 |
| Strade pedonabili Pisa | OpenStreetMap | Filtro `walk` network |
| Portici/arcate | OSM tag `covered=yes` | Ombra fissa, non dipende dal sole |
| Posizione sole | `pysolar` (calcolo locale) | Nessuna API esterna |
| Geocoding | Nominatim (OSM) | Free, no API key. Rate-limit lato server + cache risultati; self-host se traffico cresce |
| Routing (entrambi) | osmnx + networkx A* | Stesso grafo per fastest e shadiest |

---

## 8. Lingua

- Default: italiano
- Toggle IT/EN in header
- Landmark names bilingue nei suggerimenti
- Nessun account, nessuna persistenza lingua (localStorage opzionale v2)

---

## 9. Fuori scope (MVP)

- Account utente / preferenze salvate
- Notifiche push
- Altezze edifici da LiDAR/CityGML (v2)
- Altre città oltre Pisa (v2)
- Modalità bici/auto
- Previsione ombra futura (meteo)
- App nativa iOS/Android

---

## 10. Stack tecnologico

| Layer | Tecnologia |
|-------|-----------|
| Frontend | React 18 + Vite + MapLibre GL JS |
| Geocoding | Nominatim (OpenStreetMap) |
| Backend | FastAPI (Python 3.11) |
| Shadow calc | pysolar + shapely + pyproj |
| Graph/routing | osmnx + networkx (un solo grafo, no OSRM) |
| Cache | File JSON su disco (Redis opzionale v2) |
| Cron | APScheduler (dentro FastAPI) o crontab |
| Deploy | Docker Compose (backend + frontend nginx) |

---

## 11. UI Reference

Mockup approvato: `docs/superpowers/specs/ui-mockup-shadow-street.png`

Layout validato:
- Mobile collapsed bottom sheet ✓
- Mobile expanded bottom sheet (mid state) ✓  
- Desktop sidebar ✓
