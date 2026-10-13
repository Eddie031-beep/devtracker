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

### Auditoría inmutable

| Método | Ruta | Quién |
|---|---|---|
| GET | `/api/projects/<id>/audit/` | Líder, evaluador del proyecto o admin (integrante normal → 403, ajeno → 404) |

Filtros opcionales: `?action=deliverable.submitted&date_from=2026-10-01&date_to=2026-10-31` (fechas `AAAA-MM-DD`). Paginado de 50 en 50 (`?page=2`).

Para registrar algo desde cualquier servicio:

```python
from apps.audit.models import Action
from apps.audit.services import log_action

log_action(request.user, Action.DELIVERABLE_STATUS_CHANGED, deliverable,
           changes={"status": {"before": "submitted", "after": "in_review"}})
```

Llámalo dentro de la misma transacción que el cambio. Las acciones válidas están en `Action`
(`apps/audit/models.py`); agregar una nueva **no** requiere migración. El historial de versiones (#19)
ya tiene reservada `Action.VERSION_CREATED`. Los registros no se pueden editar ni borrar
(modelo, queryset, admin de solo lectura y triggers en la base de datos).

Reglas generales: proyecto ajeno → **404**, sin permiso → **403**, datos o transición inválidos → **400**.
El borrado es lógico: nada se pierde de la base de datos.

Correr las pruebas: `python manage.py test`

## Despliegue (Railway, staging)

URL de staging: https://devtracker-production-fd93.up.railway.app

Cada merge a `develop` se despliega solo. Antes de publicar, Railway corre `migrate`;
si `/api/health/` no responde 200, mantiene la versión anterior.

**Configuración del servicio `devtracker`** (en *Settings* de Railway, no en el repo):

| Campo | Valor |
|---|---|
| Source → Branch | `develop` |
| Custom Start Command | `sh -c 'python manage.py collectstatic --noinput && gunicorn config.wsgi --access-logfile -'` |
| Pre-deploy step | `sh -c 'for i in 1 2 3 4 5 6; do python manage.py migrate --noinput && exit 0; echo "Postgres despertando, reintento $i"; sleep 10; done; exit 1'` |
| Pre-deploy Timeout | `300` |
| Healthcheck Path | `/api/health/` |
| Networking | dominio generado (`settings.py` lo agrega solo a `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`) |

**Variables del servicio** (en *Variables → Raw Editor*):

| Variable | Valor |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` |
| `SECRET_KEY` | una clave larga y aleatoria (no la de `.env.example`) |
| `DEBUG` | `False` |

> ⚠️ Railway sugiere variables leídas de `.env.example` (`localhost`, `DEBUG=True`): no las agregues.
> Después de cambiar variables hay que darle a **Deploy** para que se apliquen.

> ℹ️ En el plan gratis, Postgres y Redis se duermen sin uso (Serverless obligatorio).
> La primera visita después de un rato puede fallar mientras despiertan: recarga la página.
> El pre-deploy reintenta el `migrate` hasta 6 veces por eso mismo.

**Crear el admin:** servicio `devtracker` → *Console* → `python manage.py createsuperuser`.

**Worker de Celery** (issue #21): nuevo servicio desde el mismo repo, con las mismas variables,
Start Command `celery -A config worker --loglevel=info`, sin dominio ni health check.

## Estructura

```
config/            settings, urls, app de Celery
apps/core/         modelos base (TimeStampedModel, SoftDeleteModel), health check
apps/accounts/     User personalizado con rol global (student / evaluator / admin)
apps/projects/     Project, ProjectMembership (rol por proyecto), Milestone, Deliverable
apps/audit/        AuditLog inmutable, `log_action(...)` y endpoint de consulta
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
| #17 | Despliegue en Railway (staging) | Eddie Man | — | #24, #25 |
| #18 | Auditoría inmutable | Harold Morales | — | — |
| #19 | Historial de versiones de entregables | Brayan Quintero | #18 | — |
| #20 | Integración GitHub (parte 1): vincular repo y webhook | Carlos Miranda | #17 | — |
| #21 | Integración GitHub (parte 2): sincronización y vínculo con integrantes | Eliecias Cubilla | #20 | — |

Orden sugerido: #17 y #18 primero; #19 y #20 en paralelo; #21 al final.
#19, #20 y #21 cambian modelos compartidos (`apps/projects/models.py`, `apps/accounts/models.py`):
avisen al grupo antes de subir migraciones.

El detalle y los criterios de aceptación de cada tarea están en los Issues del repo.
Lee [CONTRIBUTING.md](CONTRIBUTING.md) antes de empezar.
