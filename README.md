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
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --reload-exclude ".venv" --reload-exclude "__pycache__"
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

## Despliegue: Render (API) + Vercel (web)

### 1) Backend en Render

1. [Render](https://dashboard.render.com) → **New** → **Web Service** → conecta el repo `CTRL_VACACIONAL_PYC`.
2. Configura:
   - **Root Directory:** `backend`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/api/health`
3. Variables de entorno (Environment):

| Variable | Valor |
|----------|--------|
| `PYTHON_VERSION` | `3.12.8` *(obligatorio: no uses 3.14)* |
| `DATABASE_URL` | URL de Neon (la misma idea que tu `.env` local) |
| `JWT_SECRET` | la clave larga que generaste |
| `AUTH_MODE` | `microsoft` |
| `MS_CLIENT_ID` | `d3590ed6-52b3-4102-aeff-aad2292ab01c` |
| `MS_AUTHORITY` | `https://login.microsoftonline.com/common` |
| `MS_SCOPE` | `openid profile email` |
| `CORS_ORIGINS` | URLs exactas de Vercel (sin barra final), p. ej. `https://ctrl-vacacional-pyc.vercel.app` |
| `CORS_ORIGIN_REGEX` | `https://ctrl-vacacional[\w.-]*\.vercel.app$` (cubre previews `…-hash-equipo.vercel.app`) |
| `EXPOSE_DOCS` | `false` |
| `ATTENDANCE_DATABASE_URL` | (opcional) BD de marcación Hik |
| `ATTENDANCE_EXCEL_SHARE_URL` | link `:x:/s/...` del Excel HIK V2 |
| `ATTENDANCE_EXCEL_REFRESH_TOKEN` | refresh token corto (script MFA abajo) |

**Excel asistencia**  
`cd backend` → `python scripts/obtener_token_excel_sharepoint.py` → pega `ATTENDANCE_EXCEL_REFRESH_TOKEN` en Render. BD primero; Excel completa días posteriores.

4. Deploy. Anota la URL pública, ej. `https://ctrl-vacacional-api.onrender.com`.

> Plan free de Render duerme el servicio tras inactividad; el primer request puede tardar ~30–60 s.

### 2) Frontend en Vercel

1. [Vercel](https://vercel.com) → **Add New Project** → importa el mismo repo.
2. Configura:
   - **Root Directory:** `frontend`
   - **Framework Preset:** Vite
   - **Build Command:** `npm run build`
   - **Output Directory:** `dist`
3. Variable de entorno:

| Variable | Valor |
|----------|--------|
| `VITE_API_URL` | URL del backend en Render **sin** barra final, ej. `https://ctrl-vacacional-api.onrender.com` |

4. Deploy. Copia la URL de Vercel.

### 3) Cruzar URLs (importante)

1. En **Render**, `CORS_ORIGINS` debe incluir la URL **exacta** de producción de Vercel (sin `/` al final).
2. Deja `CORS_ORIGIN_REGEX` para los deploys de preview (`https://ctrl-vacacional-<hash>-….vercel.app`).
3. Redeploy en Render (o “Manual Deploy”) para aplicar CORS. Comprueba `/api/version` → `deploy: cors-vercel-previews`.
4. Si cambiaste el dominio de Vercel, actualiza también `VITE_API_URL` y vuelve a desplegar el front.

### Checklist rápido

- No subas `.env` (ya está en `.gitignore`)
- Un solo proceso/worker en Render (default OK; no pongas varios workers)
- Health opcional más estricto: `/api/health/db`
