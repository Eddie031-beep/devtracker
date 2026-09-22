# DevTracker

Plataforma de Gestión y Auditoría de Proyectos de Software — Proyecto Final de
**Desarrollo de Software VIII** (Universidad Tecnológica de Panamá).

**Integrantes:** Eddie Man, Carlos Miranda, Harold Morales, Brayan Quintero, Eliecias Cubilla

## Stack

Django 5.1 · Django REST Framework · SimpleJWT · PostgreSQL · Celery + Redis

## Puesta en marcha

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d               # Postgres + Redis (sin Docker: borra DATABASE_URL de .env y se usa SQLite)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- Admin: http://localhost:8000/admin/
- Health check: http://localhost:8000/api/health/
- JWT: `POST /api/auth/token/` y `POST /api/auth/token/refresh/`

Correr las pruebas: `python manage.py test`

## Estructura

```
config/            settings, urls
apps/core/         modelos base (TimeStampedModel, SoftDeleteModel), health check
apps/accounts/     User personalizado con rol global (student / evaluator / admin)
apps/projects/     Project, ProjectMembership (rol por proyecto), Milestone, Deliverable
```

## Plan por etapas

| Etapa | Contenido | Estado |
|---|---|---|
| **1. Seguridad y estructura base** | Auth + RBAC + recuperación de contraseña, permisos por proyecto, CRUD proyectos/hitos/entregables, asignación de integrantes, flujo de estados | 🚧 En curso |
| 2. Trazabilidad y entregables | Historial de versiones, auditoría inmutable, integración GitHub | ⏳ |
| 3. Métricas y evaluación | Métricas por integrante, dashboard por rol, evaluación | ⏳ |
| 4. Should / Could Have | Notificaciones, reportes, OAuth2, docs de API, extras | ⏳ |

### Etapa 1: quién hace qué

| # | Tarea | Responsable |
|---|---|---|
| 0 | Estructura base, modelo de datos, CI | Eddie Man |
| 1 | Autenticación, RBAC global y recuperación de contraseña | Carlos Miranda |
| 2 | Permisos a nivel de proyecto | Harold Morales |
| 3 | CRUD de proyectos, hitos y entregables | Brayan Quintero |
| 4 | Asignación de integrantes y responsabilidades | Eliecias Cubilla |
| 5 | Flujo de estados de entregables | Eddie Man |

El detalle y los criterios de aceptación de cada tarea están en los Issues del repo.
Lee [CONTRIBUTING.md](CONTRIBUTING.md) antes de empezar.
