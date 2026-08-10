# Microservicio de Ingesta — Job Search

> Microservicio interno que alimenta la base de datos de empleos.
> **No sirve endpoints al usuario. No tiene UI. No tiene autenticación de usuario.**
> Solo: Telegram → parse → guardar en DB.

---

## Repositorios del ecosistema

Open Ai Jobs Search es un **sistema multi-repositorio**: el proyecto completo
está compuesto por 4 repositorios que comparten la base de datos (Supabase).

| Repositorio | Rol | Puerto |
|---|---|---|
| [**Frontend (Next.js)**](https://github.com/AntonyML/open-ai-jobs-search-nextjs-frontend) | UI de usuario | `:3000` |
| [**Backend FastAPI**](https://github.com/AntonyML/open-ai-jobs-search-FastAPI-backend) | API principal + LLM Orchestrator | `:8000` |
| [**Microservicio de Ingesta**](https://github.com/AntonyML/open-ai-jobs-search-microservice-searchjobs-backend) | Telegram → `ingested_jobs` (sin LLM) — **este repo** | `:8001` |
| [**Microservicio de Ranking**](https://github.com/AntonyML/open-ai-jobs-search-microservice-rankjobs-backend) | Cola de ranking con LLM (LOAD/RANK/SAVE) | `:8002` |

---

## Qué es

Este microservicio se conecta a canales públicos de Telegram,
extrae publicaciones de empleo, las normaliza a una estructura
genérica y las guarda en la tabla `ingested_jobs` de Supabase.

La API principal (FastAPI) lee de esa tabla para responder
a la búsqueda de empleo del usuario.

```
Telegram → [Este microservicio] → DB (ingested_jobs) ← [API Principal] ← Frontend
```

---

## Qué NO es

- ❌ No es un scraper de portales de empleo.
- ❌ No usa APIs públicas de empleo (Adzuna, Indeed, Jooble).
- ❌ No usa LLM para parsing (solo regex + plantillas deterministas).
- ❌ No sirve datos al frontend directamente.
- ❌ No sabe qué es un "usuario", un "pipeline" o un "perfil".
- ❌ No tiene autenticación JWT. Es un servicio interno.

---

## Stack

| Componente | Tecnología |
|---|---|
| Framework | FastAPI (async) |
| DB | Supabase (PostgreSQL + asyncpg) |
| Migraciones | Alembic (async, tabla propia `alembic_version_ingest`) |
| Telegram | Telethon (MTProto, api_id/api_hash) |
| Parsing | Regex + plantillas por canal (sin LLM) |
| Alertas | Resend (email a admins si grupos caen) |
| Runtime | Python 3.12+ |

---

## Arquitectura

```
┌─────────────────────────────────────────────────┐
│  Microservicio de Ingesta                       │
│                                                 │
│  ┌───────────────┐   ┌───────────────────────┐ │
│  │ Group Registry│   │ Parser Engine         │ │
│  │ (categorías,  │   │ (regex templates      │ │
│  │  grupos,      │──▶│  por canal:           │ │
│  │  backups,     │   │  stem_latam,          │ │
│  │  prioridades) │   │  structured_emoji,    │ │
│  └───────────────┘   │  freetext, etc.)      │ │
│                      └───────────┬───────────┘ │
│  ┌───────────────┐              │             │
│  │ Redundancy    │              ▼             │
│  │ Chain         │   ┌───────────────────────┐ │
│  │ (P1→B1→B2    │   │ Normalizer + Dedup    │ │
│  │  →email)      │   │ (ParsedJob → hash →  │ │
│  └───────────────┘   │  INSERT if new)       │ │
│                      └───────────┬───────────┘ │
│  ┌───────────────┐              │             │
│  │ Demand        │              ▼             │
│  │ Scheduler     │   ┌───────────────────────┐ │
│  │ (frecuencia   │   │ Supabase              │ │
│  │  según uso)   │   │ ingested_jobs (TTL)   │ │
│  └───────────────┘   │ ingest_jobs (cola)    │ │
│                      │ group_health          │ │
│  ┌───────────────┐   └───────────────────────┘ │
│  │ TTL Cleaner   │                             │
│  │ (borra jobs   │                             │
│  │  >72h)        │                             │
│  └───────────────┘                             │
└─────────────────────────────────────────────────┘
```

---

## Contrato con la API principal

| Este microservicio | API Principal |
|---|---|
| ESCRIBE en `ingested_jobs` | LEE de `ingested_jobs` |
| ESCRIBE en `ingest_jobs` | LEE de `ingest_jobs` (status) |
| ESCRIBE en `group_health` | No toca |
| No toca `users`, `profiles`, etc. | No escribe en tablas de ingesta |
| No sabe de JWT ni usuarios | No sabe de Telegram ni grupos |

**Sincronización**: DB compartida. Sin callbacks. Sin webhooks.
El microservicio INSERTA, la API hace SELECT.

### Cómo la dispara la API principal

Cuando `POST /api/v1/jobs/search` (API principal) devuelve **menos de 5 resultados**, la API llama a
`POST /api/v1/ingest` con `category_id` + `keywords` para refrescar la data. La URL se configura en la
API principal con `INGEST_SERVICE_URL` (default `http://localhost:8001`).

La categoría se infiere de la búsqueda del usuario: `stem_cr`, `stem_dk`, `latam_remote`,
`freelance_intl`, `from_work_home` (default `stem_cr`). Mientras la ingesta corre, el frontend consulta
`GET /api/v1/jobs/search/{ingest_job_id}/status` y vuelve a buscar cuando el job termina (`done`).

---

## Setup

### Requisitos

- Python 3.12+
- Cuenta en [my.telegram.org](https://my.telegram.org) → `api_id` + `api_hash`
- Proyecto Supabase con connection string asyncpg
- Cuenta Resend (para alertas por email)

### Instalación

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # Linux/Mac
pip install -e .
```

### Variables de entorno

```bash
cp .env.example .env
```

| Variable | Descripción |
|---|---|
| `DATABASE_URL` | Connection string Supabase (igual que API principal) |
| `TELEGRAM_API_ID` | De my.telegram.org |
| `TELEGRAM_API_HASH` | De my.telegram.org |
| `RESEND_API_KEY` | Para alertas por email |
| `ADMIN_ALERT_EMAIL` | Email del admin para notificaciones |

### Sesión de Telethon (una vez)

```bash
python scripts/setup_telegram.py
```

Te pedirá número de teléfono + código de verificación.
Genera el archivo `sessions/ingesta.session`.

### Migraciones

```bash
# Crear tablas
alembic upgrade head

# Ver estado
alembic current

# Nueva migración (tras cambiar models.py)
alembic revision --autogenerate -m "descripción"
```

### Arranque

```bash
# Desarrollo
uvicorn app.main:app --port 8001 --reload

# Producción (1 worker — la cola interna maneja concurrencia)
uvicorn app.main:app --port 8001 --workers 1
```

> ⚙️ La **API principal** debe apuntar a este servicio con `INGEST_SERVICE_URL=http://localhost:8001` (o la URL de despliegue) en su `.env`.

---

## Endpoints (internos, no públicos)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/v1/health` | Liveness probe |
| POST | `/api/v1/ingest` | Disparar ingesta de una categoría |
| GET | `/api/v1/ingest/{job_id}/status` | Estado de un job de ingesta |
| GET | `/api/v1/jobs/search` | Buscar jobs en DB (cache) |

> Sin autenticación. Son internos.
> La API principal los consume vía red privada o localhost.

---

## Estructura del proyecto

```
├── alembic/
│   ├── env.py                 # Config async para asyncpg
│   ├── script.py.mako
│   └── versions/
│       └── 001_initial_tables.py
├── alembic.ini
├── app/
│   ├── main.py                # FastAPI app factory + lifespan
│   ├── config.py              # Settings via pydantic-settings
│   ├── database.py            # async engine + session factory
│   ├── models.py              # JobPosting, IngestJob, GroupHealth
│   ├── schemas.py             # Pydantic models
│   ├── registry.py            # GROUP_REGISTRY (categorías + grupos)
│   ├── parsing.py             # Regex parsers + dedup
│   ├── telegram.py            # Telethon wrapper
│   ├── ingestion.py           # Orchestrator + redundancy chain
│   ├── ttl.py                 # TTL cleaner
│   ├── alert.py               # Resend email alerts
│   └── routes.py              # API endpoints
├── scripts/
│   ├── setup_telegram.py      # Generar sesión Telethon
│   └── checklist.py           # Test de verificación (8 puntos)
├── sessions/
├── .env.example
├── pyproject.toml
└── README.md
```

---

## Tablas

### `ingested_jobs`

| Columna | Tipo | Descripción |
|---|---|---|
| id | String(36) PK | UUID |
| title | String(300) | Título del trabajo |
| company | String(200) | Empresa |
| location | String(200) | Ubicación |
| url | String(500) | URL original |
| description | Text | Descripción |
| salary | String(100) | Rango salarial |
| portal | String(50) | "linkedin", etc. |
| category_id | String(50) | "stem_cr", "stem_dk" |
| source_channel | String(100) | Canal Telegram |
| source_message_id | Integer | ID del mensaje |
| raw_text | Text | Texto original |
| dedup_hash | String(64) UNIQUE | SHA256(company+title+location) |
| ingested_at | DateTime(tz) | Cuándo se ingirió |
| expires_at | DateTime(tz) | ingested_at + 72h |

### `ingest_jobs` (cola)

| Columna | Tipo | Descripción |
|---|---|---|
| id | String(36) PK | UUID |
| category_id | String(50) | Categoría a buscar |
| keywords | String(300) | Keywords |
| status | String(20) | queued → running → done/failed |
| result_count | Integer | Jobs ingeridos |
| error | Text | Error si falló |
| created_at | DateTime(tz) | Creación |
| completed_at | DateTime(tz) | Finalización |

### `group_health`

| Columna | Tipo | Descripción |
|---|---|---|
| id | Integer PK | Auto-incremental |
| group_id | String(50) | ID en registry |
| status | String(20) | active/degraded/down |
| consecutive_failures | Integer | Fallos seguidos |
| failure_reason | Text | Causa del fallo |
| last_success | DateTime(tz) | Último éxito |
| checked_at | DateTime(tz) | Última verificación |

---

## Flujo de ingesta

```
POST /ingest {"category_id": "stem_cr"}
  │
  ▼
1. Crear IngestJob (status=queued)
  │
  ▼
2. Demand Scheduler: ¿toca refrescar?
  ├── NO → devolver jobs existentes
  └── SÍ → continuar
  │
  ▼
3. Redundancy Chain:
  ├── primary (STEMJobsLATAM)
  │   ├── Éxito → parse → guardar
  │   └── Fallo (3 seguidos) → marcar down → backup1
  ├── backup1
  │   ├── Éxito → parse → guardar
  │   └── Fallo → backup2
  ├── backup2
  │   ├── Éxito → parse → guardar
  │   └── Fallo → EMAIL ADMIN
  └── Todos caídos → IngestJob.status = failed
  │
  ▼
4. Parser según format_template:
  stem_latam / structured_emoji / freetext → ParsedJob
  │
  ▼
5. Dedup: SHA256 hash → INSERT si nuevo
  │
  ▼
6. IngestJob.status = done, result_count = N
```

---

## TTL y limpieza

- Jobs expiran a las **72 horas** de `ingested_at`
- Task periódico cada 6h: `DELETE FROM ingested_jobs WHERE expires_at < NOW()`
- Razón: datos frescos, menos almacenamiento, menos exposición legal

---

## Redundancia

Cada categoría tiene **mínimo 3 grupos** en el registry:

```
priority 1 (primary) → priority 2 (backup1) → priority 3 (backup2) → email admin
```

- Un grupo se marca `down` tras **3 fallos consecutivos**
- Si los 3 están down → email vía Resend al admin

---

## Demand Scheduler

| demand_score | Intervalo |
|---|---|
| 0–5 | 24 horas |
| 5–20 | 12 horas |
| 20–50 | 6 horas |
| 50+ | 3 horas |

El `demand_score` se incrementa con cada request. Categorías muy usadas se refrescan más.

---

## Parsing (sin LLM)

Parsing 100% determinista: regex + plantillas por canal.

Cuando se agrega un canal nuevo:
1. Leer 20-30 mensajes manualmente
2. Identificar el patrón
3. Asignar `format_template` existente o crear uno nuevo
4. Escribir la regex y testear con mensajes reales

**No hay LLM en este microservicio. No hay excepciones.**

---

## Decisiones de diseño

| Decisión | Razón |
|---|---|
| Telethon (MTProto) en vez de `t.me/s/` scraping | API oficial, sin fragilidad HTML |
| Sin LLM | Velocidad, costo cero, predecibilidad |
| DB compartida con API principal | Sincronización simple: INSERT + SELECT |
| Sin callbacks/webhooks | Resiliencia: si la API cae, no se pierde nada |
| TTL 72h | Datos frescos, menos exposición legal |
| 1 worker | Carga baja. Cola interna maneja concurrencia |
| Alembic propio (`alembic_version_ingest`) | No interfiere con migraciones de API principal |
| Registry en código, no en DB | Grupos cambian poco. Deploy = actualizar registry |

---
