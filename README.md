# FloorPlan Ergonomics

🏠 **2D floor plan editor with ergonomic analysis** — Design floor layouts and analyze walkability, room comfort, and traffic flow.

[![Django](https://img.shields.io/badge/Django-5.2.10-green)](https://www.djangoproject.com/)
[![Vue](https://img.shields.io/badge/Vue-3.5.24-green)](https://vuejs.org/)
[![Tailwind](https://img.shields.io/badge/Tailwind-v4-blue)](https://tailwindcss.com/)
[![PrimeVue](https://img.shields.io/badge/PrimeVue-4.x-purple)](https://primevue.org/)
[![License](https://img.shields.io/badge/License-MIT-blue)](#license)

---

## 🎯 Features

### ✅ MVP (Current)
- 📐 **Floor Plan Editor** — Draw walls, furniture, doors in 2D SVG canvas
- 🎨 **Interactive UI** — Mode selector (Select/Wall/Object/Door)
- 💾 **Save/Load** — REST API backend with SQLite
- 📊 **Grid System** — 5cm grid rasterization for ergonomic analysis
- 🌙 **Dark Mode** — Full theme support

### 🔜 Coming Soon
- 🚶 **Movement Analysis** — Calculate walkability paths (BFS algorithm)
- 🔴 **Collision Detection** — Detect narrow passages and blocked areas
- 📋 **Furniture Templates** — Prebuilt sofa, bed, table, desk objects
- 📈 **Statistics** — Room capacity, traffic flow metrics
- 🎯 **Ergonomic Checks** — Natural light access, ventilation analysis

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.10+** (for backend)
- **Node.js 18+** (for frontend)
- **Git**

### Backend Setup (Django 5.2)

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

✅ API available at: `http://localhost:8000/api/layouts/`

### Frontend Setup (Vue 3 + Tailwind v4)

```bash
cd frontend
npm install
npm run dev
```

✅ App available at: `http://localhost:5173`

---

## 📋 Project Structure

```
floorplan-ergonomics/
├── .github/
│   └── copilot-instructions.md  # AI assistant instructions
│
├── backend/                      # Django REST API
│   ├── project_config/
│   │   ├── settings.py          # Django configuration (CORS, DRF)
│   │   ├── urls.py              # API routing
│   │   ├── wsgi.py
│   │   └── asgi.py
│   ├── api/                     # Main app (layouts CRUD)
│   │   ├── models.py            # Layout model (JSONField)
│   │   ├── serializers.py       # DRF serializers
│   │   ├── views.py             # LayoutViewSet
│   │   ├── urls.py              # API endpoints
│   │   ├── migrations/
│   │   └── tests.py
│   ├── manage.py
│   ├── requirements.txt          # Python dependencies
│   └── db.sqlite3               # SQLite database
│
├── frontend/                     # Vue 3 + TypeScript SPA
│   ├── src/
│   │   ├── main.ts              # Vue app bootstrap
│   │   ├── App.vue              # Root component
│   │   ├── style.css            # Tailwind imports
│   │   ├─── api/
│   │   │   └── layoutApi.ts     # Axios HTTP client
│   │   ├── types/
│   │   │   └── layout.ts        # TypeScript interfaces
│   │   ├── stores/
│   │   │   └── layoutStore.ts   # Pinia state management
│   │   ├── components/
│   │   │   ├── Toolbar.vue      # Top bar (Save, New, Dark mode)
│   │   │   ├── Sidebar.vue      # Left panel (modes, layouts list)
│   │   │   └── FloorCanvas.vue  # SVG editor
│   │   └── assets/
│   ├── vite.config.ts           # Vite + @tailwindcss/vite config
│   ├── tailwind.config.ts       # Tailwind v4 configuration
│   ├── tsconfig.json
│   ├── package.json
│   └── index.html
│
├── .gitignore
├── .git/
├── README.md
├── floorplan-ergonomics.code-workspace
└── LICENSE

```

---

## 🛠 Tech Stack

### Backend
| Technology | Version | Purpose |
|-----------|---------|---------|
| **Django** | 5.2.10 | Web framework |
| **Django REST Framework** | 3.14.0 | REST API |
| **Django CORS Headers** | 4.3.1 | CORS support |
| **SQLite** | - | Development database |
| **PostgreSQL** | - | Production database |
| **Python** | 3.10+ | Language |

### Frontend
| Technology | Version | Purpose |
|-----------|---------|---------|
| **Vue** | 3.5.24 | UI framework |
| **TypeScript** | ~5.9.3 | Type safety |
| **Vite** | 7.3.1 | Build tool |
| **Tailwind CSS** | v4 | Utility-first CSS |
| **@tailwindcss/vite** | latest | Vite plugin |
| **PrimeVue** | 4.x | Component library |
| **Pinia** | latest | State management |
| **Axios** | latest | HTTP client |

---

## 📡 API Endpoints

### Layouts
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/layouts/` | List all layouts |
| POST | `/api/layouts/` | Create new layout |
| GET | `/api/layouts/{id}/` | Get layout details |
| PUT | `/api/layouts/{id}/` | Update layout |
| DELETE | `/api/layouts/{id}/` | Delete layout |

### Example Request

```bash
# Create layout
curl -X POST http://localhost:8000/api/layouts/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Living Room",
    "layout_data": {
      "width_cm": 500,
      "height_cm": 400,
      "walls": [{"x1": 0, "y1": 0, "x2": 500, "y2": 0}],
      "objects": [],
      "doors": []
    }
  }'
```

---

## 🔧 Development

### Running Both Servers (2 Terminals)

**Terminal 1 - Backend:**
```powershell
cd backend
.\venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

**Terminal 2 - Frontend:**
```powershell
cd frontend
npm run dev
```

### Environment Variables

Create `.env` in `backend/`:
```env
DEBUG=True
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:5174
```

### Database Migrations

```bash
cd backend
python manage.py makemigrations
python manage.py migrate
```

### Creating Admin User

```bash
cd backend
python manage.py createsuperuser
# Then visit http://localhost:8000/admin/
```

---

## 🧪 Testing

### Backend Tests
```bash
cd backend
python manage.py test api/
```

### Frontend Tests (future)
```bash
cd frontend
npm run test
```

---

## 📦 Building for Production

### Backend
```bash
cd backend
pip install gunicorn
gunicorn project_config.wsgi:application --bind 0.0.0.0:8000
```

### Frontend
```bash
cd frontend
npm run build
# Output: dist/
```

---

## 🚢 Deployment

### Railway (Recommended)
1. Push to GitHub
2. Connect repository to Railway
3. Add buildpacks: Python, Node.js
4. Set environment variables
5. Deploy!

### Docker (Alternative)
```bash
docker-compose up -d
```

---

## 📚 Documentation

- **Backend** → See `backend/README.md` (if exists)
- **Frontend** → See `frontend/README.md` (if exists)
- **AI Instructions** → See `.github/copilot-instructions.md`

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📝 License

This project is licensed under the MIT License — see [LICENSE](LICENSE) file for details.

---

## 👨‍💻 Author

**FloorPlan Ergonomics** — Created with ❤️ for better living spaces

---

## 🔗 Links

- [Django Documentation](https://docs.djangoproject.com/)
- [Vue 3 Guide](https://vuejs.org/)
- [Tailwind CSS v4](https://tailwindcss.com/)
- [PrimeVue Components](https://primevue.org/)

---

## ❓ FAQ

**Q: Can I use this on macOS/Linux?**  
A: Yes! All commands work cross-platform. Use `python3` and `source venv/bin/activate` on Unix systems.

**Q: How do I reset the database?**  
A: Delete `backend/db.sqlite3` and run `python manage.py migrate`

**Q: Can I run this without Docker?**  
A: Yes! Follow the Quick Start section — no Docker required.

---

**Last Updated:** January 23, 2026
