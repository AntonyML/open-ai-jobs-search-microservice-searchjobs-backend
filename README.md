# CVMeld — Microservicio de Ingesta

> Ingesta de ofertas de empleo para CVMeld. Telegram → parse → DB.

Microservicio interno que alimenta la tabla `ingested_jobs` de CVMeld.
**No sirve endpoints al usuario. No tiene UI. No tiene autenticación de usuario.**

```
Telegram → [Este microservicio] → DB (ingested_jobs) ← [API principal] ← Frontend
```

## Qué es

- Se conecta a canales públicos de Telegram, extrae publicaciones de empleo, las normaliza y las guarda en Supabase.
- Parsing 100% determinista (regex + plantillas por canal). **Sin LLM.**
- TTL de 72 h: datos frescos, menos exposición legal.

## Stack

FastAPI (async) · Supabase/asyncpg · Alembic · Telethon · Resend · Python 3.12+

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e .
cp .env.example .env    # DATABASE_URL, TELEGRAM_API_ID/HASH, RESEND_API_KEY
python scripts/setup_telegram.py   # una vez: genera sessions/ingesta.session
alembic upgrade head
uvicorn app.main:app --port 8001
```

## Endpoints (internos)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/v1/health` | Liveness probe |
| POST | `/api/v1/ingest` | Disparar ingesta de una categoría |
| GET | `/api/v1/ingest/{job_id}/status` | Estado de un job |
| GET | `/api/v1/jobs/search` | Buscar jobs en DB |

> Sin autenticación. Los consume la API principal vía `INGEST_SERVICE_URL`.

## Estructura

```
app/main.py       FastAPI app factory + lifespan
app/registry.py   GROUP_REGISTRY (categorías + grupos)
app/parsing.py    regex parsers + dedup
app/telegram.py   wrapper Telethon
app/ingestion.py  orquestador + cadena de redundancia
app/ttl.py        limpiador de jobs expirados
scripts/          setup_telegram.py, checklist.py
```

## Ecosistema

| Repositorio | Rol |
|---|---|
| [cvmeld-frontend](https://github.com/AntonyML/cvmeld-frontend) | UI de usuario |
| [cvmeld-fastapi-backend](https://github.com/AntonyML/cvmeld-fastapi-backend) | API principal + LLM |
| **cvmeld-searchjobs-backend** | Ingesta — este repo |
| [cvmeld-rankjobs-backend](https://github.com/AntonyML/cvmeld-rankjobs-backend) | Ranking con LLM |