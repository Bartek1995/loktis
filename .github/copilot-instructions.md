# Instrukcje dla Asystenta AI - Analizator Ogloszen

## Django 5.2 + Django REST Framework + Vue 3 + TypeScript + PrimeVue

*Jezyk odpowiedzi: ZAWSZE po polsku*

---

## 0. Cel aplikacji

Analizator Ogloszen Nieruchomosci - MVP do szybkiej analizy ogloszen mieszkaniowych.

### Flow uzytkownika

1. Uzytkownik wkleja link do ogloszenia (Otodom/OLX)
2. System pobiera dane z ogloszenia (tytul, cena, metraz, pokoje, lokalizacja)
3. Jesli jest lokalizacja - analiza okolicy przez Overpass API
4. Generowanie raportu z TL;DR, danymi, scoring okolicy, checklista

---

## 1. Struktura projektu

### Backend
```
backend/listing_analyzer/
  providers/      # Parsery ogloszen (Otodom, OLX)
  geo/            # Overpass client, POI analyzer
  models.py       # AnalysisResult
  views.py        # API endpoints
  services.py     # Glowny serwis analizy
  report_builder.py
  cache.py        # In-memory TTL cache
  rate_limiter.py
```

### Frontend
```
frontend/src/
  api/analyzerApi.ts
  views/analyzer/
    LandingView.vue
    ReportView.vue
```

---

## 2. Komendy

### Backend
```powershell
cd backend
. .\venv\Scripts\Activate.ps1
python manage.py runserver 0.0.0.0:8000
```

### Frontend
```powershell
cd frontend
npm run dev
```

---

## 3. API Endpoints

| Metoda | Endpoint | Opis |
|--------|----------|------|
| POST | /api/analyze/ | Analizuje ogloszenie |
| POST | /api/validate-url/ | Waliduje URL |
| GET | /api/providers/ | Lista providerow |
| GET | /api/history/ | Historia analiz |

---

## 4. Zasady stylowania (Frontend)

- Uzywaj TYLKO komponentow PrimeVue
- Tailwind tylko do layoutu (grid, flex, gap)
- NIE dodawaj recznych kolorow (bg-*, text-*)

---

## 5. Dodawanie nowego providera

1. Utworz plik w listing_analyzer/providers/
2. Dziedzicz po BaseProvider
3. Zaimplementuj can_handle() i parse()
4. Dodaj do registry.py
