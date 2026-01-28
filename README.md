# 🏠 Analizator Ogłoszeń Nieruchomości

Aplikacja do szybkiej analizy ogłoszeń mieszkaniowych z serwisów **Otodom** i **OLX** z oceną okolicy w oparciu o OpenStreetMap.

![Vue.js](https://img.shields.io/badge/Vue.js-3.x-4FC08D?logo=vuedotjs)
![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django)
![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?logo=typescript)
![License](https://img.shields.io/badge/License-MIT-blue)

## ✨ Funkcjonalności

- **📊 Parsowanie ogłoszeń** - automatyczne pobieranie danych z Otodom i OLX (tytuł, cena, metraż, pokoje, piętro, lokalizacja, zdjęcia)
- **🗺️ Analiza okolicy** - integracja z OpenStreetMap/Overpass API dla POI w konfigurowalnym promieniu (250-1000m)
- **📈 Scoring okolicy** - automatyczna ocena infrastruktury z podziałem na kategorie:
  - 🛒 Sklepy | 🚌 Transport | 🎓 Edukacja | 🏥 Zdrowie | 🌳 Rekreacja | 🍽️ Gastronomia | 🏦 Finanse
- **🔇 Quiet Score** - ocena poziomu ciszy/hałasu na podstawie obecności głośnych obiektów
- **🗺️ Interaktywna mapa** - Leaflet z kolorowymi markerami POI i radius overlay
- **⚡ Streaming w czasie rzeczywistym** - aktualizacje statusu podczas analizy (NDJSON)
- **📝 Raport z analizy** - TL;DR (3 plusy + 3 ryzyka), szczegóły ogłoszenia, mapa POI

## 🏗️ Architektura

### Backend (Django 5.2 + DRF)

```
backend/
├── listing_analyzer/
│   ├── providers/           # Parsery ogłoszeń
│   │   ├── base.py          # Bazowy provider
│   │   ├── otodom.py        # Parser Otodom
│   │   ├── olx.py           # Parser OLX
│   │   └── registry.py      # Rejestr providerów
│   ├── geo/                 # Analiza geograficzna
│   │   ├── overpass_client.py   # Klient Overpass API
│   │   └── poi_analyzer.py      # Scoring okolicy + Quiet Score
│   ├── models.py            # Model AnalysisResult
│   ├── views.py             # Endpointy API (w tym streaming)
│   ├── services.py          # Główny serwis analizy
│   ├── report_builder.py    # Budowanie raportów
│   ├── cache.py             # In-memory cache TTL
│   ├── rate_limiter.py      # Rate limiting
│   └── urls.py              # Routing
└── project_config/
    ├── settings.py
    └── urls.py
```

### Frontend (Vue 3 + TypeScript + PrimeVue + Leaflet)

```
frontend/src/
├── api/
│   └── analyzerApi.ts       # Klient API + streaming
├── views/
│   └── analyzer/
│       ├── LandingView.vue  # Strona główna z formularzem + radius toggle
│       └── ReportView.vue   # Wyświetlanie raportu + mapa Leaflet
├── router/
│   └── index.ts
└── App.vue
```

## 🚀 Uruchomienie

### Backend

```powershell
cd backend

# Aktywuj venv
.\venv\Scripts\Activate.ps1

# Zainstaluj zależności
pip install -r requirements.txt

# Migracje
python manage.py makemigrations listing_analyzer
python manage.py migrate

# Uruchom serwer
python manage.py runserver 0.0.0.0:8000
```

### Frontend

```powershell
cd frontend

# Zainstaluj zależności
npm install

# Uruchom dev server
npm run dev
```

**Aplikacja dostępna pod:**
- 🌐 Frontend: http://localhost:5173
- 🔌 Backend API: http://localhost:8000/api/

## 📡 API Endpoints

| Metoda | Endpoint | Opis |
|--------|----------|------|
| `POST` | `/api/analyze/` | Analizuje ogłoszenie (streaming NDJSON) |
| `POST` | `/api/validate-url/` | Waliduje URL przed analizą |
| `GET` | `/api/providers/` | Lista obsługiwanych serwisów |
| `GET` | `/api/history/` | Historia analiz |
| `GET` | `/api/history/{id}/` | Szczegóły analizy |
| `GET` | `/api/history/{id}/report/` | Pełny raport z historii |
| `GET` | `/api/history/recent/` | Ostatnie 10 analiz |

### Przykład request do analizy

```json
POST /api/analyze/
{
  "url": "https://www.otodom.pl/pl/oferta/...",
  "radius": 500,
  "use_cache": true
}
```

### Streaming response (NDJSON)

```json
{"status": "validating", "message": "Walidacja URL..."}
{"status": "parsing", "message": "Pobieranie ogłoszenia..."}
{"status": "map", "message": "Analiza mapy (promień 500m)..."}
{"status": "calculating", "message": "Obliczanie wyników..."}
{"status": "generating", "message": "Generowanie raportu końcowego..."}
{"status": "complete", "result": {...}}
```

## ⚙️ Konfiguracja

### Rate Limiting
- 5 requestów / minuta
- 30 requestów / godzina

### Cache TTL
- Wyniki parsowania: **1 godzina**
- Dane z Overpass API: **24 godziny**

### Promień analizy
- Minimum: 250m
- Maximum: 1000m
- Domyślnie: 500m

## 📦 Technologie

| Warstwa | Technologia |
|---------|-------------|
| Frontend | Vue 3, TypeScript, PrimeVue, Tailwind CSS, Leaflet |
| Backend | Django 5.2, Django REST Framework, BeautifulSoup4 |
| Mapy | Leaflet, OpenStreetMap, Overpass API |
| Build | Vite, npm |

## ⚠️ Uwagi

- Scraping może być niestabilny - serwisy mogą zmieniać strukturę HTML
- Aplikacja zwraca partial result nawet gdy niektóre dane się nie pobiorą
- Dane z OpenStreetMap mogą być niekompletne dla niektórych lokalizacji
- Analiza ma charakter poglądowy i nie zastępuje własnej weryfikacji
- Quiet Score bazuje na obecności potencjalnie głośnych obiektów (bary, kluby, główne drogi)

## 📄 Licencja

MIT License
