# Instrukcje dla Asystenta AI – floorplan-ergonomics
## Django 5.2 + Django REST Framework + Vue 3 + TypeScript + PrimeVue
*Język odpowiedzi: ZAWSZE po polsku*

---

## 0. Cel dokumentu

Ten dokument definiuje *precyzyjne zasady generowania kodu i analiz* dla aplikacji floor plan ergonomics:

- **Backend**: Django 5.2.10 + Django REST Framework 3.14.0
- **Frontend**: Vue 3 + TypeScript + PrimeVue (latest) + Pinia
- **Baza danych**: SQLite (dev) / PostgreSQL (prod)
- **Architektura**: REST API + SPA
- **Klucz domeny**: `Layout` (model przechowujący dane planu piętra jako JSON)

*Cel nadrzędny*:
- poprawność domenowa > estetyka
- logika biznesowa po stronie backendu (Django)
- frontend to UI dla API

---

## 1. Złote zasady (globalne)

1. *Nie zgaduj*
   - Brak danych → poproś wprost:
     - „Pokaż payload / endpoint"
     - „Jaki to model / serializer?"
     - „Gdzie teraz uruchamiasz?"
   - Wstrzymaj odpowiedź zamiast generować domysły.

2. *Jedno źródło prawdy*
   - Walidacja i reguły biznesowe → *Django / DRF*
   - Frontend → walidacja Zod odzwierciedlająca backend (opcjonalnie)

3. *Czytelność > spryt*
   - Kod ma być łatwy do czytania i debugowania.

---

## 2. Środowisko i komendy (Windows PowerShell)

### Backend (Django)

```powershell
$VENV_PY = "C:\Projects\floorplan-ergonomics\backend\venv\Scripts\python.exe"
$PROJ_DIR = "C:\Projects\floorplan-ergonomics\backend"
```

*Zawsze:*
- najpierw Set-Location $PROJ_DIR
- zawsze używaj $VENV_PY
- nigdy systemowego pythona

### Szablony komend (Backend)

```powershell
# Ogólne
Set-Location $PROJ_DIR; & $VENV_PY manage.py <komenda>

# Runserver
Set-Location $PROJ_DIR; & $VENV_PY manage.py runserver 0.0.0.0:8000

# Makemigrations + migrate
Set-Location $PROJ_DIR; & $VENV_PY manage.py makemigrations
Set-Location $PROJ_DIR; & $VENV_PY manage.py migrate --no-input

# Shell
Set-Location $PROJ_DIR; & $VENV_PY manage.py shell --command "kod"
```

### Frontend (Vue/Vite + Tailwind v4 + PrimeVue)

**ŚCIEŻKA PRAWIDŁOWA:**
```powershell
# ✅ PRAWIDŁOWO - uruchamianie dev server
Set-Location c:\Projects\floorplan-ergonomics\frontend; npm run dev
npm run dev
# → Serwer na http://localhost:5173

# ✅ PRAWIDŁOWO - build produkcji
cd c:\Projects\floorplan-ergonomics\frontend
npm run build

# ✅ PRAWIDŁOWO - preview built
cd c:\Projects\floorplan-ergonomics\frontend
npm run preview
```

**⚠️ BŁĘDY do UNIKANIA:**
```powershell
# ❌ BŁĄD - brak cd do folderu
npm run dev

# ❌ BŁĄD - Set-Location w PowerShell może nie działać prawidłowo
Set-Location $FE_DIR; npm run dev
```

**Stack frontendowy:**
- **Vite** - bundler (v7.3.1)
- **Vue 3** - framework
- **TypeScript** - type safety
- **Tailwind CSS v4** - @tailwindcss/vite plugin
- **PrimeVue** - UI components (v4)
- **Pinia** - state management
- **Axios** - HTTP client

---

## 3. Backend – Django 5.2 + DRF

### 3.1 Struktura projektu

```
backend/
├─ project_config/           # projekt Django (startproject)
│  ├─ settings.py           # konfiguracja
│  ├─ urls.py               # routing główny
│  ├─ asgi.py / wsgi.py
│  └─ __init__.py
├─ layout_editor/            # aplikacja domenowa (moduł)
│  ├─ models.py             # model Layout
│  ├─ admin.py              # admin interface
│  ├─ apps.py
│  ├─ migrations/           # migracje
│  ├─ serializers.py        # LayoutSerializer (DRF)
│  ├─ views.py              # LayoutViewSet
│  ├─ urls.py               # API endpoints dla layout_editor
│  ├─ permissions.py        # (opcjonalnie) uprawnienia
│  ├─ tests.py              # testy modułu
│  └─ __init__.py
├─ analysis/                 # aplikacja domenowa (moduł)
│  ├─ models.py             # AnalysisResult, itp.
│  ├─ serializers.py        # serializery
│  ├─ views.py              # widoki analizy
│  ├─ urls.py               # API endpoints
│  ├─ tests.py
│  └─ __init__.py
├─ manage.py
├─ requirements.txt          # zależności
└─ venv/                     # virtual environment
```

**Zasada**: Każdy katalog (layout_editor, analysis, ...) to samodzielna aplikacja Django z:
- własnymi modelami
- własnymi serializers
- własnymi views / ViewSets
- własnymi URLs (urls.py)
- testami (tests.py)

W `project_config/urls.py` jest routing główny, który include'uje URLs z każdego modułu.

### 3.2 Modele – layout_editor (`layout_editor/models.py`)

Model `Layout`:
- `name` – CharField (nazwa planu)
- `layout_data` – JSONField (geometria: ściany, obiekty, wymiary)
- `created_at`, `updated_at` – timestamps

**Reguła**: Layout przechowuje całą geometrię jako JSON (ściany, obiekty, grid, wymiary).

```python
# layout_editor/models.py
class Layout(models.Model):
    name = models.CharField(max_length=255, default="Unnamed Layout")
    layout_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
```

### 3.2.1 Dodatkowe modele – analysis (opcjonalnie)

```python
# analysis/models.py
class AnalysisResult(models.Model):
    layout = models.ForeignKey('layout_editor.Layout', on_delete=models.CASCADE)
    collision_count = models.IntegerField(default=0)
    narrow_passages = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

### 3.3 Serializery – layout_editor (`layout_editor/serializers.py`)

- Logika domenowa *zawsze w serializerze lub modelu*
- Serializacja / deserializacja JSON layout_data
- Walidacja payloadu (wymiary, nazwy)

```python
# layout_editor/serializers.py
from rest_framework import serializers
from .models import Layout

class LayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Layout
        fields = ['id', 'name', 'layout_data', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
```

### 3.3.1 Serializery – analysis (opcjonalnie)

```python
# analysis/serializers.py
class AnalysisResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisResult
        fields = ['id', 'layout', 'collision_count', 'narrow_passages', 'created_at']
        read_only_fields = ['id', 'created_at']
```

### 3.4 ViewSets – layout_editor (`layout_editor/views.py`)

- CRUD na Layout
- Filtry: by name, by created_at
- Bez kompleksnych obliczeń (grid analysis w frontendzie lub analysis module)

```python
# layout_editor/views.py
from rest_framework import viewsets
from .models import Layout
from .serializers import LayoutSerializer

class LayoutViewSet(viewsets.ModelViewSet):
    queryset = Layout.objects.all()
    serializer_class = LayoutSerializer
    filterset_fields = ['name', 'created_at']
    search_fields = ['name']
```

### 3.4.1 ViewSets – analysis (opcjonalnie)

```python
# analysis/views.py
class AnalysisViewSet(viewsets.ViewSet):
    def create(self, request):
        # Pobierz layout_id z request
        # Uruchom analizę (BFS, kolizje, wąskie przejścia)
        # Zwróć wynik jako AnalysisResult
        pass
```

### 3.5 API Endpoints – routing

**project_config/urls.py** (główny routing):
```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/layout/', include('layout_editor.urls')),       # /api/layout/...
    path('api/analysis/', include('analysis.urls')),         # /api/analysis/...
]
```

**layout_editor/urls.py**:
```python
from rest_framework.routers import DefaultRouter
from .views import LayoutViewSet

router = DefaultRouter()
router.register(r'layouts', LayoutViewSet)

urlpatterns = router.urls
```

**analysis/urls.py**:
```python
from rest_framework.routers import DefaultRouter
from .views import AnalysisViewSet

router = DefaultRouter()
router.register(r'results', AnalysisViewSet)

urlpatterns = router.urls
```

### 3.5.1 Dostępne endpointy

| Metoda | Endpoint                      | Opis                    | Moduł          |
|--------|-------------------------------|------------------------|-----------------|
| GET    | /api/layout/layouts/          | Lista planów            | layout_editor   |
| POST   | /api/layout/layouts/          | Utwórz plan             | layout_editor   |
| GET    | /api/layout/layouts/{id}/     | Pobierz plan            | layout_editor   |
| PUT    | /api/layout/layouts/{id}/     | Zaktualizuj plan        | layout_editor   |
| DELETE | /api/layout/layouts/{id}/     | Usuń plan               | layout_editor   |
| POST   | /api/analysis/results/        | Uruchom analizę         | analysis        |
| GET    | /api/analysis/results/{id}/   | Pobierz wynik analizy   | analysis        |

### 3.6 CORS i settings

Ustawienia w `project_config/settings.py`:
- CORS dla localhost:5173
- REST_FRAMEWORK config (pagination, filtering)
- INSTALLED_APPS: rest_framework, corsheaders, django_filters, layout_editor, analysis

---

## 4. Frontend – Vue 3 + TypeScript + Tailwind v4 + PrimeVue

### 4.1 Struktura projektu

```
frontend/
├─ package.json
├─ vite.config.ts              # @tailwindcss/vite plugin
├─ tailwind.config.ts          # Tailwind v4 (bez PostCSS plugin'u)
├─ tsconfig.json
├─ index.html
├─ src/
│  ├─ main.ts                  # bootstrap Vue + PrimeVue + Pinia
│  ├─ App.vue                  # root komponent (layout)
│  ├─ style.css                # @import "tailwindcss"
│  ├─ api/
│  │  └─ layoutApi.ts          # klient HTTP (axios)
│  ├─ types/
│  │  └─ layout.ts             # TypeScript types (Layout, Wall, FloorObject, Door)
│  ├─ stores/
│  │  └─ layoutStore.ts        # Pinia store (stan layoutu + actions)
│  ├─ components/
│  │  ├─ Toolbar.vue           # top bar + save/new/export/dark-mode
│  │  ├─ Sidebar.vue           # lista planów + info + mode selector
│  │  └─ FloorCanvas.vue       # SVG editor (walls, objects, doors, grid)
│  └─ assets/                  # obrazy, itp.
└─ public/
```

### 4.2 Technologia

| Pakiet | Wersja | Opis |
|--------|--------|------|
| **Vite** | 7.3.1 | Bundler |
| **Vue** | 3.5.24 | Framework |
| **TypeScript** | ~5.9.3 | Type safety |
| **Tailwind CSS** | v4 (latest) | @tailwindcss/vite plugin |
| **PrimeVue** | 4.x | Komponenty UI (Button, Card, Dialog, Sidebar, etc.) |
| **Pinia** | latest | State management |
| **Axios** | latest | HTTP client |

### 4.3 Komponenty PrimeVue w użyciu

**App.vue:**
- Layout z Toolbar (top) + Sidebar (left) + Canvas (center)

**Toolbar.vue:**
- Button (icons: file-edit, save, download, moon/sun)
- Tooltip (krótkie opisy)
- Divider (separatory)

**Sidebar.vue:**
- Card (sekcje)
- Button (mode selector: Wybór, Ściana, Obiekt, Drzwi)
- ProgressSpinner (loading)
- ScrollPanel (lista planów)

**FloorCanvas.vue:**
- SVG native (canvas)
- Button (zoom +/-, reset)
- ToggleButton (grid on/off)

### 4.4 API Integracja

```typescript
// layoutApi.ts
const api = axios.create({ baseURL: 'http://localhost:8000/api' })

export const layoutApi = {
  listLayouts: () => api.get<Layout[]>('/layouts/'),
  getLayout: (id: number) => api.get<Layout>(`/layouts/${id}/`),
  createLayout: (data) => api.post<Layout>('/layouts/', data),
  updateLayout: (id: number, data) => api.put<Layout>(`/layouts/${id}/`, data),
  deleteLayout: (id: number) => api.delete(`/layouts/${id}/`),
}
```

### 4.5 Pinia Store

```typescript
// layoutStore.ts
export const useLayoutStore = defineStore('layout', () => {
  const layouts = ref<Layout[]>([])
  const currentLayout = ref<Layout | null>(null)
  const mode = ref<'wall' | 'object' | 'door' | 'select'>('wall')
  const scale = ref(1)
  const showGrid = ref(true)

  // Actions: fetchLayouts, createLayout, saveLayout, addWall, etc.
})
```

### 4.6 Build i dev

```powershell
cd c:\Projects\floorplan-ergonomics\frontend

# Dev
npm run dev       # Vite dev server na http://localhost:5173

# Prod
npm run build     # Production build
npm run preview   # Preview built
```

---

## 5. Helpery i composables

### 5.1 Zasada nadrzędna

Nie twórz helpera ani composable domyślnie.
Helpery i composables są dozwolone tylko wtedy, gdy realnie poprawiają czytelność i redukują duplikację.

### 5.2 Kiedy helper/composable jest WSKAZANY

- logika powtarza się w 2+ miejscach
- logika jest podatna na błędy (np. normalizacja JSON layoutu)
- logika jest przekrojowa (używana w wielu widokach)

### 5.3 Kiedy helper/composable jest ZAKAZANY

- logika jest ściśle UI-specyficzna dla jednego komponentu
- to tylko 1–3 linie oczywistego kodu
- byłby to „wrapper na wrapper"

### 5.4 Gdzie umieszczać

- *Globalne*: src/core/ (jeśli będzie)
- *Domenowe*: src/api/, src/stores/, obok komponentów

---

## 6. Komponenty Vue

- Zanim stworzysz nowy komponent: sprawdź czy już istnieje
- Preferuj PrimeVue komponenty (Button, Card, Dialog, Tree, itp.)
- Zakaz: any, nadmiarowych watch (preferuj computed)

---

## 7. Formularze i walidacja

### 7.1 Źródło walidacji

1. *Backend (DRF serializer)* – prawda absolutna
2. Frontend – opcjonalnie Zod, ale backend zawsze sprawdza

---

## 8. Dane (payload JSON)

### 8.1 Struktura layout_data

Przykład payload wysyłany do backendu:

```json
{
  "name": "Living Room",
  "layout_data": {
    "width_cm": 500,
    "height_cm": 400,
    "walls": [
      {"x1": 0, "y1": 0, "x2": 500, "y2": 0},
      {"x1": 500, "y1": 0, "x2": 500, "y2": 400}
    ],
    "objects": [
      {"x": 100, "y": 100, "w": 80, "h": 60, "type": "sofa"},
      {"x": 300, "y": 150, "w": 60, "h": 40, "type": "table"}
    ],
    "grid_cells": {
      "width": 100,
      "height": 80,
      "occupied": [[0,1,1,0], [0,1,1,0], ...]
    }
  }
}
```

---

## 9. Testy

### 9.1 Backend (Django)

*Minimalny zestaw testów na zmianę modelu/API:*

- test create (happy path)
- test ograniczeń (null, blank, unique)
- test API statusów (200, 201, 400, 403, 404)
- test wydajności (brak N+1)

Umieść testy w `api/tests.py` lub katalog `api/tests/`.

### 9.2 Frontend (Vue)

*Testuj tylko:*
- krytyczne przepływy UI (np. save do API)
- mapowanie błędów API → toast

---

## 10. Zmiana wymogów / edge-case'i

Zawsze rozważ:
- null, brak pola, pusty string
- nieistniejący ID
- strefy czasowe (created_at)
- wymiary 0 lub ujemne
- grid collision edge-cases

---

## 11. Debug – format raportu

1. **Objawy** (co nie działa)
2. **Przyczyna** (konkretna linia / warunek)
3. **Naprawa** (konkretna zmiana)
4. **Zapobieganie** (test, linter)
5. **Ryzyka** (N+1, XSS, race conditions)

---

## 12. Nowa biblioteka

```
// Dlaczego: [powód]
// Zalety: [czemu wybrana]
// Wady: [możliwe problemy]
// Alternatywy: [co innego można użyć]
```

---

## 13. MVP – Priority (do realizacji)

| Task | Status | Opis |
|------|--------|------|
| Frontend init | ✅ | Vite + Vue3 + PrimeVue |
| Backend init | ✅ | Django 5.2 + DRF + Layout model |
| Rasteryzacja | ⏳ | Grid 5cm, BFS, kolizje |
| Save/Load | ⏳ | Podpięcie API (App.vue → backend) |
| Grid analysis | ⏳ | Algorytm wąskich przejść |
| Furniture templates | ⏳ | Predefiniowane obiekty (sofa, łóżko, itp.) |
| Deployment | ⏳ | Railway + PostgreSQL |

---

## 14. Komendy quick-start

### Uruchomienie wszystkiego (2 terminale)

**Terminal 1 – Backend:**
```powershell
cd C:\Projects\floorplan-ergonomics\backend
.\venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

**Terminal 2 – Frontend:**
```powershell
cd C:\Projects\floorplan-ergonomics\frontend
npm run dev
```

✅ **Backend:** http://localhost:8000  
✅ **Backend API:** http://localhost:8000/api/layouts/  
✅ **Frontend:** http://localhost:5173  

### Troubleshooting

**Port 5173 zajęty?**
- Vite automatycznie przejdzie na 5174, 5175, etc.
- Sprawdź na `http://localhost:5174`

**Brak połączenia z API?**
- Upewnij się że backend działa na 8000
- Sprawdź CORS w `backend/project_config/settings.py`
- Konsola przeglądarki (F12) pokaże błędy

---

## 15. Kontakt domenowy

**layout_editor – moduł zarządzania planami:**
- *Co*: przechowuje plan piętra (geometrię, obiekty, wymiary)
- *Gdzie*: backend/layout_editor/ (models, serializers, views)
- *API*: /api/layout/layouts/ (CRUD)
- *Models*: Layout

**analysis – moduł analizy (opcjonalnie):**
- *Co*: analizuje grid (BFS, kolizje, wąskie przejścia)
- *Gdzie*: backend/analysis/
- *API*: /api/analysis/results/
- *Models*: AnalysisResult

**Edytor (FloorCanvas):**
- *Co*: rysuje ściany, obiekty; rasteryzuje grid; wykrywa kolizje
- *Gdzie*: frontend/src/components/FloorCanvas.vue

**State:**
- *Co*: aktualny layout (ściany, obiekty, ustawienia)
- *Gdzie*: frontend/src/stores/layoutStore.ts (Pinia)

**HTTP:**
- *Co*: komunikacja frontend ↔ backend
- *Gdzie*: frontend/src/api/layoutApi.ts
- *Backend*: layout_editor/urls.py, analysis/urls.py (DRF Router)

---

## 16. Dobre praktyki (podsumowanie)

✅ DO:
- Backend first (model + serializer → API)
- Frontend konsumuje API
- JSON jako single source of truth (layout_data)
- Testy dla zmian na backendu
- Jasne nazwy zmiennych / funkcji
- Komentarze tylko dla WHY (nie WHAT)

❌ NIE:
- Duplikacja logiki frontend ↔ backend
- Zgadywanie bez sprawdzenia kodu
- any w TypeScript
- N+1 queries
- Helper/composable bez uzasadnienia
- Zmiany bez testów

---

*Ostatnia aktualizacja: 2026-01-23*  
*Projekt: floorplan-ergonomics*  
*Stack: Django 5.2.10 + Vue 3 + PrimeVue*
