# DevTracker

Plataforma de Gestión y Auditoría de Proyectos de Software — Proyecto Final de
**Desarrollo de Software VIII** (Universidad Tecnológica de Panamá).

**Integrantes:** Eddie Man, Carlos Miranda, Harold Morales, Brayan Quintero, Eliecias Cubilla

## Stack

Django 5.1 · Django REST Framework · SimpleJWT · PostgreSQL · Celery + Redis · Railway (gunicorn + WhiteNoise)

## Puesta en marcha
> ⚠️ **Problemas comunes**
> - Si el admin se ve sin estilos: falta el archivo `.env` (necesita `DEBUG=True`).
> - Si las pruebas o el servidor se quedan colgados: el `.env` tiene `DATABASE_URL` y no hay Postgres corriendo. Borra esa línea.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Sin Docker: en .env borra la línea DATABASE_URL (se usa SQLite)
# Con Docker: docker compose up -d   (Postgres + Redis)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- Admin: http://localhost:8000/admin/
- Health check: http://localhost:8000/api/health/
- JWT: `POST /api/auth/token/` y `POST /api/auth/token/refresh/`

### Endpoints de autenticación

| Método | Ruta | Quién |
|---|---|---|
| POST | `/api/auth/register/` | Público (se crea como estudiante) |
| POST | `/api/auth/token/` | Público (login) |
| POST | `/api/auth/logout/` | Autenticado (envía `refresh`) |
| GET | `/api/auth/me/` | Autenticado |
| POST | `/api/auth/password-reset/` | Público (envía `email`) |
| POST | `/api/auth/password-reset/confirm/` | Público (`uid`, `token`, `new_password`) |
| GET | `/api/auth/users/` | Admin |
| PATCH | `/api/auth/users/<id>/role/` | Admin (`global_role`) |

En desarrollo el correo de recuperación se imprime en la consola del `runserver`.
Permisos reutilizables en `apps/accounts/permissions.py`: `IsAdmin`, `IsEvaluator`, `IsStudent`.

### Endpoints de proyectos

| Método | Ruta | Quién |
|---|---|---|
| GET, POST | `/api/projects/` | Autenticado (al crear, queda como líder) |
| GET, PATCH, DELETE | `/api/projects/<id>/` | Ver: integrante · Editar/borrar: líder |
| GET, POST | `/api/milestones/` | Ver: integrante · Crear: líder |
| GET, PATCH, DELETE | `/api/milestones/<id>/` | Ver: integrante · Editar/borrar: líder |
| GET, POST | `/api/deliverables/` | Ver: integrante · Crear: líder |
| GET, PATCH, DELETE | `/api/deliverables/<id>/` | Ver: integrante · Editar/borrar: líder |

### Endpoints de integrantes

| Método | Ruta | Quién |
|---|---|---|
| GET | `/api/projects/<id>/members/` | Integrante |
| POST | `/api/projects/<id>/members/` | Líder (`email`, `role`, `responsibilities`) |
| PATCH, DELETE | `/api/projects/<id>/members/<membership_id>/` | Líder |
| PUT | `/api/deliverables/<id>/assignees/` | Líder (`{"assignees": [ids]}`) |

### Flujo de entregables

| Método | Ruta | Quién |
|---|---|---|
| POST | `/api/deliverables/<id>/submit/` | Integrante asignado (el sistema decide a tiempo o tardío) |
| POST | `/api/deliverables/<id>/status/` | Evaluador o líder (`{"status": "in_review" / "approved" / "rejected"}`) |

Reglas generales: proyecto ajeno → **404**, sin permiso → **403**, datos o transición inválidos → **400**.
El borrado es lógico: nada se pierde de la base de datos.

Correr las pruebas: `python manage.py test`

## Despliegue (Railway, staging)

La configuración está en el repo: `railway.json` (web) y `railway.worker.json` (Celery).
En cada deploy Railway corre `migrate` antes de arrancar, junta los estáticos (los sirve WhiteNoise)
y levanta `gunicorn`. Si `/api/health/` no responde 200, el deploy no se publica.

**Primera vez (lo hace el líder):**

1. En Railway: *New Project → Deploy from GitHub repo* → `devtracker`.
   En *Settings* del servicio, rama `develop` (cada merge a `develop` se despliega solo).
2. *+ New → Database*: agrega **PostgreSQL** y **Redis** al mismo proyecto.
3. En *Variables* del servicio web:

   | Variable | Valor |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
   | `REDIS_URL` | `${{Redis.REDIS_URL}}` |
   | `SECRET_KEY` | una clave larga y aleatoria (no la de `.env.example`) |
   | `DEBUG` | `False` |

4. *Settings → Networking → Generate Domain*. Railway expone ese dominio en
   `RAILWAY_PUBLIC_DOMAIN` y `settings.py` lo agrega solo a `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`.
5. Crear el admin: `railway ssh` (en el servicio web) y luego `python manage.py createsuperuser`.

**Worker de Celery** (cuando haya tareas, issue #21): *+ New → GitHub repo* con el mismo repo,
en *Settings → Config-as-code* apunta a `railway.worker.json` y copia las mismas variables.

URL de staging: _pendiente_

## Estructura

```
config/            settings, urls, app de Celery
apps/core/         modelos base (TimeStampedModel, SoftDeleteModel), health check
apps/accounts/     User personalizado con rol global (student / evaluator / admin)
apps/projects/     Project, ProjectMembership (rol por proyecto), Milestone, Deliverable
```

## Plan por etapas

| Etapa | Contenido | Estado |
|---|---|---|
| **1. Seguridad y estructura base** | Auth + RBAC + recuperación de contraseña, permisos por proyecto, CRUD proyectos/hitos/entregables, asignación de integrantes, flujo de estados | ✅  Completa |
| **2. Trazabilidad y entregables** | Historial de versiones, auditoría inmutable, integración GitHub, despliegue en Railway | 🚧 En curso |
| 3. Métricas y evaluación | Métricas por integrante, dashboard por rol, evaluación | ⏳ |
| 4. Should / Could Have | Notificaciones, reportes, OAuth2, docs de API, extras | ⏳ |

### Etapa 1: quién hace qué

| Issue | Tarea | Responsable | PR |
|---|---|---|---|
| #6 | Estructura base, modelo de datos, CI | Eddie Man | — |
| #1 | Autenticación, RBAC global y recuperación de contraseña | Carlos Miranda | #7 |
| #2 | Permisos a nivel de proyecto | Harold Morales | #10 |
| #3 | CRUD de proyectos, hitos y entregables | Brayan Quintero, Harold Morales | #10, #11 |
| #4 | Asignación de integrantes y responsabilidades | Eliecias Cubilla | #9, #12 |
| #5 | Flujo de estados de entregables | Eddie Man | #8, #13 |

### Etapa 2: quién hace qué

| Issue | Tarea | Responsable | Depende de | PR |
|---|---|---|---|---|
| #17 | Despliegue en Railway (staging) | Eddie Man | — | — |
| #18 | Auditoría inmutable | Harold Morales | — | — |
| #19 | Historial de versiones de entregables | Brayan Quintero | #18 | — |
| #20 | Integración GitHub (parte 1): vincular repo y webhook | Carlos Miranda | #17 | — |
| #21 | Integración GitHub (parte 2): sincronización y vínculo con integrantes | Eliecias Cubilla | #20 | — |

Orden sugerido: #17 y #18 primero; #19 y #20 en paralelo; #21 al final.
#19, #20 y #21 cambian modelos compartidos (`apps/projects/models.py`, `apps/accounts/models.py`):
avisen al grupo antes de subir migraciones.

El detalle y los criterios de aceptación de cada tarea están en los Issues del repo.
Lee [CONTRIBUTING.md](CONTRIBUTING.md) antes de empezar.
