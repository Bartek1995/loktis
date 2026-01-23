# Backend - floorplan-ergonomics

Django + DRF REST API dla projektu floor plan analyzer.

## Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows

# Zainstaluj dependencje
pip install -r requirements.txt

# Migracje
python manage.py migrate

# Runserver
python manage.py runserver
```

Server: `http://localhost:8000`
API: `http://localhost:8000/api/`

## Endpoints

- `GET /api/layouts/` - lista layoutów
- `POST /api/layouts/` - utwórz layout
- `GET /api/layouts/{id}/` - pobierz layout
- `PUT /api/layouts/{id}/` - update
- `DELETE /api/layouts/{id}/` - usuń
