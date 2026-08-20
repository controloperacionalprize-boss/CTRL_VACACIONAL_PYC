# Planificador de vacaciones (React + FastAPI + Neon)

## Arranque local

1. Copia `.env.example` → `.env` en la raíz y completa Neon + `JWT_SECRET`.
2. (Opcional) Copia `frontend/.env.example` → `frontend/.env` si el API no está en el mismo origen.
3. Backend:

```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

4. Frontend:

```
cd frontend
npm install
npm run dev
```

Abre http://localhost:5173 e inicia sesión con Microsoft (código de dispositivo). El correo debe existir en la tabla `users`.

Health checks: `/api/health` (proceso) y `/api/health/db` (Neon).

## Qué no se sube a git

- `.env` / `frontend/.env` (secretos)
- `backend/.venv/`, `frontend/node_modules/`, `frontend/dist/`
- Excel (`*.xlsx`) y `backend/sql/carga_datos.sql`

## Carga inicial desde Excel

```
cd backend
python scripts/generar_sql_neon.py           # genera backend/sql/carga_datos.sql
python scripts/generar_sql_neon.py --apply   # aplica directo a Neon
```

Instalación vacía de tablas: ejecuta `backend/sql/schema.sql` en el SQL Editor de Neon.

## Despliegue (checklist)

- `DATABASE_URL` y `JWT_SECRET` propios (no reutilizar los de desarrollo)
- `CORS_ORIGINS` con el dominio real del frontend
- `VITE_API_URL` apuntando al backend público al hacer `npm run build`
- Backend con **un solo worker/proceso** (el login Microsoft guarda el flujo en memoria)
- Opcional: health check de la plataforma → `/api/health/db`
