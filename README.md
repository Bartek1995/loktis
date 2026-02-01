# 🌍 Loktis – Location Intelligence Platform

Loktis to narzędzie decyzyjne typu **location intelligence**, które odpowiada na pytanie:

> **„Czy ta lokalizacja jest dobra do życia lub inwestowania — dziś i w perspektywie 3–5 lat?”**

W przeciwieństwie do klasycznych portali nieruchomości:
- nie promujemy ogłoszeń,
- nie optymalizujemy pod kliknięcia,
- **wydajemy werdykt oparty na danych**.

Nie oceniamy mieszkania.  
**Oceniamy ryzyko i potencjał lokalizacji.**

---

## ✅ Aktualny stan projektu (MVP)

### 1. Location-First Analysis
**Status:** ✅ ZAIMPLEMENTOWANE  
**Ciężkość wdrożenia:** 🟢 Niska (gotowe)

- Klik na mapie → cena / metraż → raport
- Flow w pełni *location-first* (bez zależności od ogłoszeń)
- Streaming NDJSON (real-time feedback)

**Wartość biznesowa:**  
To fundament projektu i główna przewaga nad portalami nieruchomości.

---

### 2. Advanced Location Scoring (POI Intelligence)
**Status:** ✅ ZAIMPLEMENTOWANE  
**Ciężkość wdrożenia:** 🟡 Średnia

- Integracja z Overpass API (cache 24h)
- Analiza POI w promieniu 500–1000 m
- Kategorie z wagami:

| Kategoria | Status | Uwagi |
|---------|------|------|
| Sklepy | ✅ | poprawne |
| Transport publiczny | ✅ | kluczowe |
| Edukacja | ✅ | krytyczne dla rodzin |
| Zdrowie | ✅ | niedoszacowane przez rynek |
| Zieleń | ✅ | silny argument sprzedażowy |
| Sport / rekreacja | ✅ | uzupełniające |
| Gastronomia | ✅ | city-life |
| Finanse | ✅ | najmniej istotne |

**Brak:** interpretacji i werdyktu (patrz sekcja raportowa).

---

### 3. Quiet Score 2.0 (Noise Intelligence)
**Status:** ✅ ZAIMPLEMENTOWANE  
**Ciężkość wdrożenia:** 🟡 Średnia

Analiza źródeł hałasu:
- drogi szybkiego ruchu,
- arterie miejskie,
- tramwaje i kolej,
- przystanki <100 m,
- życie nocne.

**Output:** skala 0–100  
**Wartość:** jeden z najmocniejszych wyróżników produktu w Polsce.

---

### 4. TL;DR Decision Generator
**Status:** ✅ ZAIMPLEMENTOWANE  
**Ciężkość wdrożenia:** 🟢 Niska

- 3 największe plusy
- 3 największe minusy
- Cena za m² vs średnia
- Infrastruktura
- Quiet Score

**Brak:** jednoznacznego werdyktu („polecane / warunkowo / niepolecane”).

---

### 5. Frontend (Vue 3)
**Status:** ✅ ZAIMPLEMENTOWANE  
**Ciężkość wdrożenia:** 🟡 Średnia

- Location picker (Leaflet)
- Live progress analizy
- Widok raportu
- Historia analiz

Frontend wystarczający do sprzedaży MVP.

---

### 6. Backend (Django 5.2)
**Status:** ✅ ZAIMPLEMENTOWANE  
**Ciężkość wdrożenia:** 🟡 Średnia

- Model `LocationAnalysis` z `public_id`
- Cache TTL (Overpass 24h, listingi 1h)
- Rate limiting
- Architektura Services / Providers
- Endpointy:
  - `POST /api/analyze-location/`
  - `GET /api/report/{public_id}/`
  - `GET /api/history/`

---

## 🚧 Brakujące elementy krytyczne (High Impact)

### 7. Profile użytkownika (Personas)
**Status:** ❌ BRAK  
**Ciężkość wdrożenia:** 🟡 Średnia  
**Impact:** 🔥 WYSOKI

Profile:
- Rodzina (cisza, szkoły, zieleń)
- Singiel / City Life (transport, gastro)
- Inwestor (płynność, ROI, studenci)

Zmieniają:
- wagi scoringu,
- narrację raportu,
- końcowy werdykt.

---

### 8. Dynamiczne wagi (Custom Scoring)
**Status:** ❌ BRAK  
**Ciężkość wdrożenia:** 🟡 Średnia  
**Impact:** 🔥 WYSOKI

- Suwaki wag kategorii
- Przeliczanie score bez ponownego Overpass
- Poczucie kontroli po stronie użytkownika

---

### 9. Weredykt decyzyjny (Decision Verdict)
**Status:** ❌ BRAK  
**Ciężkość wdrożenia:** 🟢 Niska  
**Impact:** 🔥🔥 BARDZO WYSOKI

Jednoznaczny output:
- ✅ Polecane
- ⚠️ Warunkowo polecane
- ❌ Niepolecane

Z uzasadnieniem opartym na danych.

---

## 🧠 Sekcje raportowe „WOW” (publiczne dane)

### 10. Ukryte ryzyka lokalizacji
**Status:** ❌ BRAK  
**Ciężkość wdrożenia:** 🟡 Średnia  
**Źródła:** dane publiczne

- Strefy hałasu (mapy akustyczne UE)
- Planowane drogi / linie kolejowe
- Lotniska w promieniu 10 km
- Strefy zalewowe (ISOK)

---

### 11. Jakość życia w czasie (3–5 lat)
**Status:** ❌ BRAK  
**Ciężkość wdrożenia:** 🟡 Średnia  
**Źródła:** GUS

- Trendy demograficzne mikro
- Starzenie się / napływ rodzin
- Charakter dzielnicy (tranzytowa vs osiadła)

---

### 12. Edukacja i infrastruktura społeczna
**Status:** ❌ BRAK  
**Ciężkość wdrożenia:** 🟡 Średnia  
**Źródła:** dane gmin / MEN

- Obłożenie szkół i przedszkoli
- Ryzyko braku miejsc

---

### 13. Środowisko i zdrowie
**Status:** ❌ BRAK  
**Ciężkość wdrożenia:** 🟢–🟡  
**Źródła:** GIOŚ

- Historyczna jakość powietrza (PM2.5 / PM10)
- Sezonowość smogu

---

### 14. Nasłonecznienie i ekspozycja
**Status:** ❌ BRAK  
**Ciężkość wdrożenia:**  
- 🟢 Prosta heurystyka  
- 🔴 Zaawansowana analiza cieni

---

## 💰 Monetyzacja (rekomendowana)

- 1 darmowy raport (bez ceny m²)
- Kolejne raporty:
  - 9–19 PLN / raport
  - pakiety (5 / 10)
- Płatności: Przelewy24 + BLIK
- Raport jako **produkt decyzyjny**, nie SaaS

---

## 🎯 Priorytety wdrożeniowe

1. Weredykt decyzyjny
2. Profile użytkownika
3. Ukryte ryzyka lokalizacji
4. Custom scoring (suwaki)
5. Nasłonecznienie
6. Konta użytkowników (dopiero po PMF)

---

> „Ten raport ma wskazać ryzyka, których nie widać podczas 15-minutowego spaceru po okolicy.”
