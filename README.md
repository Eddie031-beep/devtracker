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

- Interfaz web (dashboard): http://localhost:8000/
- Documentación de la API (Swagger): http://localhost:8000/api/docs/
- Admin: http://localhost:8000/admin/
- Health check: http://localhost:8000/api/health/
- JWT: `POST /api/auth/token/` y `POST /api/auth/token/refresh/`

### Tailwind CSS (módulos del semestral)

Las pantallas nuevas (incidencias, riesgos, cambios de alcance, reuniones) usan **Tailwind CSS**.
Se compila con el CLI standalone de Tailwind, **sin Node**:

```bash
./scripts/build_css.sh           # genera apps/web/static/web/tailwind.css
./scripts/build_css.sh --watch   # recompila mientras editas plantillas
```

- El binario se descarga solo la primera vez en `.bin/` (ignorado por git).
- `tailwind.css` compilado se sube al repo: Railway no necesita compilar nada. El CI falla si quedó viejo.
- Las clases llevan el prefijo `tw-` (`tw-flex`, `tw-gap-4`) para no chocar con `app.css`, y no se usa el
  *preflight*, así las pantallas anteriores se ven igual. Los colores (`tw-bg-card`, `tw-text-muted`...) usan
  las variables de `app.css`, por eso el modo oscuro funciona sin cambios.
- Piezas comunes (`dt-card`, `dt-chip`, `dt-table`, `dt-tab`...) en `tailwind/input.css`.

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
| POST | `/api/deliverables/<id>/submit/` | Integrante asignado (el sistema decide a tiempo o tardío; requiere `url`, `comment` opcional) |
| POST | `/api/deliverables/<id>/status/` | Evaluador o líder (`{"status": "in_review" / "approved" / "rejected"}`) |

### Historial de versiones

| Método | Ruta | Quién |
|---|---|---|
| POST | `/api/deliverables/<id>/submit/` | Integrante asignado (`{"url": "https://...", "comment": "..."}`). Cada entrega o reentrega genera una versión correlativa inmutable |
| GET | `/api/deliverables/<id>/versions/` | Integrante del proyecto (cualquier rol dentro del proyecto; ajeno → 404, sin autenticar → 401) |

Solo se guardan enlaces (`url` a PR, release, Google Drive, etc.), no archivos en disco, ya que el almacenamiento de Railway se borra en cada despliegue. Las versiones son estrictamente inmutables.

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

### Integración con GitHub (webhook)

| Método | Ruta | Quién |
|---|---|---|
| PATCH | `/api/projects/<id>/` | Líder (`github_repo` como `owner/repo` y `github_webhook_secret`) |
| POST | `/api/integrations/github/webhook/<project_id>/` | Público, pero exige la firma HMAC de GitHub (`X-Hub-Signature-256`) |

Cada push al repo vinculado queda registrado como commits del proyecto (modelo `Commit` en
`apps/integrations/`, visible en el admin). Firma inválida o proyecto sin secreto → **403**;
push de un repo distinto al vinculado → **400**; un commit que ya estaba registrado se ignora sin error
(la respuesta indica cuántos se crearon: `{"detail": "ok", "created": 2}`). El evento `ping` responde
`pong` y cualquier otro evento se ignora con 200. El secreto nunca se devuelve en la API: solo
`has_github_webhook_secret`.

**Cómo configurarlo:**

1. Genera un secreto largo: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Como líder del proyecto, guárdalo en DevTracker junto con el repo:

   ```bash
   curl -X PATCH https://devtracker-production-fd93.up.railway.app/api/projects/<id>/ \
     -H "Authorization: Bearer <access>" -H "Content-Type: application/json" \
     -d '{"github_repo": "owner/repo", "github_webhook_secret": "<secreto>"}'
   ```

3. En GitHub: repo → *Settings* → *Webhooks* → *Add webhook*:

   | Campo | Valor |
   |---|---|
   | Payload URL | `https://devtracker-production-fd93.up.railway.app/api/integrations/github/webhook/<id>/` |
   | Content type | `application/json` (obligatorio) |
   | Secret | el mismo secreto del paso 1 |
   | SSL verification | Enable |
   | Which events | *Let me select individual events* → **Pushes** y **Pull requests** |

4. Al guardar, GitHub manda un `ping`: en *Recent Deliveries* debe verse un 200. Haz un push y los
   commits aparecen en el admin (*Integrations → Commits*). Si sale 403, el secreto no coincide.

> ℹ️ Se registran los commits de todas las ramas. GitHub incluye como máximo 20 commits por push en el
> webhook; para lo anterior está la sincronización (abajo).
> Para probar en local, GitHub no llega a `localhost`: usa staging o un túnel (p. ej. `ngrok`).

### Commits por integrante y entregable

| Método | Ruta | Quién |
|---|---|---|
| PATCH | `/api/auth/me/` | Autenticado (`{"github_username": "mi-usuario"}`; es lo único editable ahí) |
| GET | `/api/projects/<id>/commits/` | Integrante del proyecto (ajeno → 404) |
| POST | `/api/projects/<id>/commits/sync/` | Líder o admin (integrante → 403). Responde **202** y la tarea corre en Celery |

Cada commit (del webhook o de la sincronización) se vincula solo:

- **Integrante:** el `github_username` del commit contra el de los integrantes del proyecto (sin
  distinguir mayúsculas); si no hay, el correo del commit contra el correo de la cuenta. Los correos
  privados `12345+usuario@users.noreply.github.com` también se reconocen. Alguien que no es integrante
  del proyecto nunca queda vinculado.
- **Entregable:** `#D<id>` en el mensaje (ej. `Agrega login #D12`), solo si el entregable 12 es de ese
  mismo proyecto y no está borrado.

Al guardar tu `github_username` en `/api/auth/me/`, tus commits anteriores sin dueño quedan vinculados.
La sincronización también completa los vínculos pendientes (p. ej. de un entregable creado después del
commit). Un vínculo que ya existe no se reemplaza.

Filtros: `?author=<user_id>`, `?deliverable=<id>` (o `none` en cualquiera de los dos para ver los sin
vincular). Paginado de 50 en 50.

La sincronización trae la rama principal del repo desde la API de GitHub (hasta 2000 commits) sin
duplicar lo que ya llegó por el webhook. Sin token, GitHub solo permite repos públicos y 60 peticiones
por hora: para repos privados agrega la variable `GITHUB_TOKEN` (token *fine-grained* con permiso de
solo lectura a *Contents* del repo). Si Redis está dormido responde **503**: reintenta en un momento.

Sin worker de Celery (como en staging), la sincronización se corre a mano desde la consola:

```bash
python manage.py sync_github_commits <id_proyecto>   # uno o varios ids
python manage.py sync_github_commits --all           # todos los proyectos con repo vinculado
```

### Pull requests e historial (estilo GitKraken)

Cada integrante trabaja en su rama y abre un PR **desde su propia cuenta de GitHub** con
`#D<id>` en el título, la descripción o el nombre de la rama (`feature/D12-dashboard`):

1. Llega el evento `pull_request` al webhook y el PR queda registrado (modelo `PullRequest`; repetir el
   evento no lo duplica, solo actualiza su estado: abierta, fusionada o cerrada).
2. Si quien lo abre es la persona **asignada** al entregable, el entregable pasa a *Entregado* y se crea
   una versión con el enlace del PR. Al líder y al evaluador les llega el aviso.
3. El profesor o revisor abre el entregable y decide: **Aprobar** (completo) o **Rechazar** (no completo,
   con retroalimentación).
4. Si fue rechazado, el siguiente push al mismo PR vuelve a entregarlo como versión nueva.

No se entrega si el PR es borrador, si la cuenta de GitHub no es de un integrante (revisa el usuario de
GitHub en *Mi perfil*) o si quien lo abre no es el asignado; la respuesta del webhook dice por qué
(*Recent Deliveries* en GitHub).

La página **Historial** del proyecto (`/proyectos/<id>/historial/`) muestra el grafo de ramas y
fusiones, la etiqueta de cada rama y PR, el entregable vinculado y el autor de cada commit, con filtros
por integrante, rama y «solo vinculados». Ahí mismo el líder tiene el botón **Sincronizar con GitHub**,
que trae commits (rama principal y demás ramas vivas, con sus padres reales) y los PR, sin entrar a la API.

### Evaluación de entregables

| Método | Ruta | Quién |
|---|---|---|
| POST | `/api/deliverables/<id>/evaluate/` | Evaluador o líder del proyecto, o admin (integrante → 403) |
| GET | `/api/deliverables/<id>/evaluations/` | Integrante del proyecto (la más reciente primero) |

```json
{"decision": "approved", "score": 92, "feedback": "Buen trabajo"}
```

- `decision`: `approved` o `rejected`; `score`: de 0 a 100; `feedback` es opcional.
- Se puede evaluar lo entregado (a tiempo o tarde) o lo que está en revisión. Si recién se entregó, pasa
  primero por «En revisión», así cada paso queda en la auditoría (`deliverable.status_changed` y
  `deliverable.evaluated`).
- Un rechazo permite reentregar (nueva versión) y volver a evaluar. Las evaluaciones no se editan ni se
  borran; la nota vigente de un entregable es la de su evaluación más reciente.

### Métricas

| Método | Ruta | Quién |
|---|---|---|
| GET | `/api/projects/<id>/metrics/` | Integrante del proyecto o admin (ajeno → 404) |

Devuelve, para el proyecto:

- **Entregables:** total, por estado, entregados, tarde, % a tiempo, aprobados, nota promedio y vencidos sin entregar.
- **Commits:** total, vinculados a entregables, sin integrante reconocido, últimos 30 días y por semana (8 semanas).
- **Por integrante:** asignados, entregados, tarde, % a tiempo, aprobados, nota promedio, versiones y commits.

### Interfaz web (dashboard por rol)

En `/` (login en `/login/` con el mismo usuario de la API):

| Rol | Ve en el inicio |
|---|---|
| Estudiante | Sus entregas pendientes (con las vencidas resaltadas) y sus proyectos |
| Evaluador o líder | Además, los entregables que esperan revisión |
| Administrador | Además, un resumen de toda la plataforma (usuarios y entregables por estado) |

- **Proyecto** (`/proyectos/<id>/`): indicadores, gráficos (entregables por estado, commits por semana y
  por integrante), tabla de métricas por integrante y entregables por hito.
- **Entregable** (`/entregables/<id>/`): estado, versiones, evaluaciones y commits vinculados. El
  asignado puede entregar y el evaluador o el líder puede evaluar desde la misma página.

Los permisos son los mismos que en la API: proyecto o entregable ajeno → 404.

**Usuarios del equipo:** `python manage.py crear_equipo --password <clave> --proyecto 1` crea (o actualiza) las
cuentas de Harold, Brayan, Carlos y Eliecias, más un evaluador `profesor`, con esa contraseña, su usuario de
GitHub, su rol en el proyecto y sus responsabilidades. Cada uno puede cambiarla después.

**Cómo participa cada uno en la web:**

| Rol | Qué hace |
|---|---|
| Líder | En el proyecto crea hitos y entregables («Nuevo hito», «Nuevo entregable») y asigna a cada integrante; aprueba o rechaza con nota |
| Integrante | Ve sus pendientes en el inicio y en *Mis entregables*, entrega con un enlace y sigue sus avisos |
| Evaluador | Ve lo que espera revisión, evalúa con nota y comentario, consulta métricas, reportes y la auditoría (`/proyectos/<id>/auditoria/`) |

**Datos de ejemplo para la demo:** `python manage.py cargar_demo --proyecto 1` crea 3 hitos y 15
entregables repartidos entre los integrantes, con entregas a tiempo y tarde, rechazos, reentregas y
evaluaciones. Usa el flujo real, así que también llena la auditoría. Si ya se cargó, no hace nada.

### Documentación de la API

- Swagger UI: `/api/docs/` · Esquema OpenAPI: `/api/schema/` (públicos: solo describen los endpoints).
- Para probar endpoints protegidos: `POST /api/auth/token/`, copia el `access` y pégalo en **Authorize**.

### Notificaciones

Avisos dentro de la app (campana **Avisos** del menú, `/notificaciones/`) y por correo con `EMAIL_BACKEND`:

| Cuándo | A quién |
|---|---|
| Se entrega un entregable (a tiempo o tarde) | Líder y evaluadores del proyecto |
| Se evalúa (aprobado o rechazado, con nota) | Los asignados |
| Te asignan un entregable | Solo los recién asignados |
| Un entregable pendiente vence pronto | Los asignados (`python manage.py enviar_recordatorios --horas 48`) |

Nadie recibe aviso de lo que hizo él mismo. Los recordatorios no se repiten el mismo día.

| Método | Ruta | Quién |
|---|---|---|
| GET | `/api/notifications/?unread=1` | Autenticado: solo sus propios avisos |
| POST | `/api/notifications/<id>/read/` | El destinatario (ajeno → 404) |
| POST | `/api/notifications/read-all/` | Autenticado |

Por defecto el correo se imprime en la consola (o en los logs de Railway). Para enviarlo de verdad, configura
`EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` y las variables `EMAIL_HOST`, etc. de Django;
`NOTIFICATIONS_SEND_EMAIL=False` lo apaga.

### Reportes

Desde la página del proyecto, sección **Reportes** (mismos permisos que el proyecto):

- **Reporte imprimible** (`/proyectos/<id>/reporte/`): resumen, desempeño por integrante y entregables;
  el botón *Imprimir / guardar como PDF* lo exporta.
- **Excel** (`devtracker.xlsx`): un libro con las hojas *Entregables*, *Integrantes* y, si quien descarga
  puede verla, *Auditoría*. Se genera sin dependencias extra y los textos nunca se interpretan como fórmulas.
- **CSV** (se abren en Excel): `entregables.csv`, `integrantes.csv` y `auditoria.csv` (este último solo
  para líder, evaluador del proyecto o admin; integrante → 403).

### Administración desde la web (sin entrar a la API)

| Página | Quién | Qué hace |
|---|---|---|
| Inicio → **Nuevo proyecto** | Líder o admin | Crea el proyecto; quien lo crea queda como líder |
| Proyecto → **Editar** | Líder o admin | Nombre, fechas, repo de GitHub; **genera el secreto del webhook** y muestra la Payload URL (una sola vez) |
| Proyecto → **Integrantes** | Líder o admin | Agregar usuario con rol y responsabilidades, cambiar rol, quitar (no deja quitar al único líder) |
| Hito → **Editar hito** / Entregable → **Editar** | Líder o admin | Editar, reasignar o **eliminar** (lógico) |

Todo pasa por las mismas reglas que la API: integrante → 403, proyecto ajeno → 404, cada cambio queda en la
auditoría y eliminar solo marca `deleted_at` (versiones, evaluaciones y auditoría se conservan). Cambiar la
fecha de un entregable no le quita la marca de «tarde».

### Recuperar contraseña

Los enlaces del correo y del calendario usan `SITE_URL` (en Railway se toma solo del dominio público; en
local es `http://localhost:8000`, cámbiala en `.env` si usas otro puerto).

En el login, **¿Olvidaste tu contraseña?** (`/recuperar/`) manda un enlace de un solo uso al correo de la
cuenta; la respuesta es la misma exista o no el correo. Con el `EMAIL_BACKEND` por defecto (consola) el
correo sale en los logs del servidor (en Railway: *Deploy Logs*). Para correo real:
`EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `EMAIL_HOST=smtp.gmail.com`,
`EMAIL_HOST_USER` y `EMAIL_HOST_PASSWORD` (contraseña de aplicación de Google).

### Modo oscuro, calendario y Gemini (Could Have)

- **Modo oscuro**: botón en el menú lateral; se recuerda en el navegador y, si no se eligió, sigue el tema
  del sistema operativo. Al imprimir siempre sale en claro.
- **Calendario iCal**: en *Mi perfil* está el enlace personal para suscribirse desde Google Calendar
  (*Otros calendarios → Desde URL*) o el botón *Descargar .ics*. Incluye los entregables asignados (o todos
  los del proyecto si eres líder o evaluador), los cierres de hito y un aviso un día antes.
- **Sugerencias con Gemini**: con `GEMINI_API_KEY` (y opcional `GEMINI_MODEL`, por defecto
  `gemini-2.5-flash`), el líder o evaluador ve en el entregable *Pedir sugerencias*: Gemini lee el texto
  del PR y los mensajes de los commits y resume qué cambia, qué podría faltar y qué revisar. No pone notas:
  aprobar o rechazar lo sigue decidiendo una persona. Sin la clave, no aparece.

### Iniciar sesión con GitHub (OAuth2) y perfil

- En **Mi perfil** (`/perfil/`, clic en tu nombre en el menú) cada usuario registra su usuario de GitHub;
  al guardarlo se le vinculan sus commits anteriores.
- **Entrar con GitHub**: GitHub confirma quién eres y DevTracker te da acceso solo si ese usuario de GitHub
  ya está registrado en un perfil. No crea cuentas nuevas.
- Para activarlo: GitHub → *Settings → Developer settings → OAuth Apps → New OAuth App* con
  *Authorization callback URL* `https://<dominio>/login/github/callback/`, y en el servidor las variables
  `GITHUB_OAUTH_CLIENT_ID` y `GITHUB_OAUTH_CLIENT_SECRET`. Sin ellas el botón no aparece.

Reglas generales: proyecto ajeno → **404**, sin permiso → **403**, datos o transición inválidos → **400**.
El borrado es lógico: nada se pierde de la base de datos.

Correr las pruebas: `python manage.py test`

## Examen semestral: módulos de gestión del proyecto

Cuatro módulos nuevos, cada uno con su página en el proyecto (sección **Gestión del proyecto**), su API
documentada en Swagger, auditoría y avisos. Las pantallas usan Tailwind CSS; las validaciones están en el
formulario (HTML5: `required`, `minlength`, rangos) **y** en el backend (formularios de Django, serializadores
y las reglas de `services.py`). Datos de ejemplo: `python manage.py cargar_semestral --proyecto 1`.

### 1. Incidencias de software

`/proyectos/<id>/incidencias/` · código `apps/issues/`

- Cualquier integrante registra un error con **título, descripción, prioridad** (baja, media, alta, crítica)
  y **pasos para reproducirlo**.
- El **líder asigna el responsable** (un integrante o el líder; nunca el evaluador).
- Estados: **Abierta → En resolución → Resuelta → Verificada**. El responsable (o el líder) la empieza y la
  marca resuelta explicando la solución.
- El **evaluador verifica** la solución o la **reabre** indicando el motivo (vuelve a *Abierta*).
- **Historial inmutable** (`IssueEvent`): cada paso, comentario y reapertura queda guardado; no se edita ni
  se borra. Además todo va a la auditoría del proyecto. Eliminar es lógico y solo lo hace el líder.
- Avisos: al líder y al evaluador cuando hay una incidencia nueva o resuelta; al responsable cuando se la
  asignan o se reabre.

| Método | Ruta | Quién |
|---|---|---|
| GET, POST | `/api/projects/<id>/issues/` | Integrante (filtros `status`, `priority`, `assignee`) |
| GET, PATCH, DELETE | `/api/issues/<id>/` | Ver: integrante · Editar: quien reportó o líder · Borrar: líder |
| POST | `/api/issues/<id>/assign/` | Líder (`assignee_id`) |
| POST | `/api/issues/<id>/transition/` | `start`/`resolve`: responsable o líder · `verify`/`reopen`: evaluador |
| GET, POST | `/api/issues/<id>/history/` | Integrante (POST agrega un comentario) |

### 2. Riesgos del proyecto

`/proyectos/<id>/riesgos/` · código `apps/risks/`

- Los estudiantes registran riesgos con **descripción, probabilidad, impacto** (1 Baja/Bajo, 2 Media/Medio,
  3 Alta/Alto) y **responsable**. El evaluador los consulta.
- **Nivel = probabilidad × impacto** (`apps/risks/matrix.py`): **Bajo** 1–2, **Medio** 3–4, **Alto** 6–9.
  Se calcula en el servidor al guardar (la base además rechaza valores fuera de 1–3) y el formulario lo
  muestra en vivo mientras se eligen los valores.
- La página muestra la **matriz 3×3** con los riesgos abiertos de cada celda; tocar una celda filtra la lista.
- **Medidas de mitigación** con responsable y fecha; se marcan cumplidas. La primera medida pone el riesgo
  *En mitigación*.
- Estados: **Identificado, En mitigación, Materializado, Cerrado** (y reabrir un cerrado). Materializarse o
  cerrarse exige comentario. Editar, cambiar el estado y mitigar: el líder o el responsable del riesgo.
- Historial en la página del riesgo (sale de la auditoría) y avisos al responsable y, si el riesgo es alto o
  se materializa, al líder y al evaluador.

| Método | Ruta | Quién |
|---|---|---|
| GET, POST | `/api/projects/<id>/risks/` | Ver: integrante · Crear: estudiante (filtros `status`, `level`) |
| GET | `/api/projects/<id>/risks/matrix/` | Integrante |
| GET, PATCH, DELETE | `/api/risks/<id>/` | Editar: líder o responsable · Borrar: líder |
| POST | `/api/risks/<id>/status/` | Líder o responsable (`status`, `comment`) |
| GET, POST | `/api/risks/<id>/mitigations/` | Crear: líder o responsable |
| POST | `/api/mitigations/<id>/done/` | Responsable de la medida, del riesgo o líder |

### 3. Solicitudes de cambio de alcance

`/proyectos/<id>/cambios/` · código `apps/scope/`

- Los **estudiantes proponen** un cambio con **descripción, justificación, impacto esperado** (texto y nivel
  bajo/medio/alto) y, si quieren, los entregables que tocaría.
- El **evaluador aprueba o rechaza** con un comentario obligatorio; la decisión guarda quién y cuándo y es
  definitiva. Quien propuso puede editarla o **retirarla** mientras está pendiente.
- **Se conserva todo**: las solicitudes no se borran (ni desde el admin) y, una vez cerradas, el modelo no
  permite modificarlas. Todo queda también en la auditoría.
- **No modifica los entregables**: la lista de entregables es solo una referencia. Si el cambio se aprueba,
  el líder los ajusta a mano y esa edición queda en la auditoría como cualquier otra.
- Avisos al evaluador y al líder con cada propuesta, y a quien propuso con la decisión.

| Método | Ruta | Quién |
|---|---|---|
| GET, POST | `/api/projects/<id>/change-requests/` | Ver: integrante · Proponer: estudiante (filtro `status`) |
| GET, PATCH | `/api/change-requests/<id>/` | Editar: quien la propuso, si está pendiente (no hay DELETE) |
| POST | `/api/change-requests/<id>/decide/` | Evaluador (`decision`: approved/rejected, `comment`) |
| POST | `/api/change-requests/<id>/withdraw/` | Quien la propuso |

### 4. Reuniones y acuerdos

`/proyectos/<id>/reuniones/` · código `apps/meetings/`

- Los estudiantes registran el **acta** de cada reunión: **fecha y hora**, lugar o enlace, **participantes**
  (integrantes del proyecto) y **resumen de los temas tratados**. La fecha no puede ser futura.
- Cada reunión tiene **acuerdos** con **responsable** (integrante o líder), **fecha de cumplimiento** y estado
  **pendiente o cumplido** (se guarda quién y cuándo lo cumplió). Un pendiente con la fecha pasada se ve
  como *Vencido*.
- **Consultar** actas y acuerdos: todos los integrantes del proyecto, incluido el evaluador (un ajeno recibe 404).
- **Actualizar** un acuerdo: solo su responsable o el líder; reasignarlo, solo el líder. Editar el acta y
  registrar acuerdos: quien la registró o el líder. Cualquier otro recibe 403.
- La lista de acuerdos se filtra por pendientes, vencidos, cumplidos, responsable o «míos». Todo queda en la
  auditoría y el responsable recibe un aviso cuando le asignan un acuerdo.

| Método | Ruta | Quién |
|---|---|---|
| GET, POST | `/api/projects/<id>/meetings/` | Ver: integrante · Registrar: estudiante (`participant_ids`) |
| GET, PATCH, DELETE | `/api/meetings/<id>/` | Editar o borrar (lógico): quien la registró o líder |
| POST | `/api/meetings/<id>/agreements/` | Quien registró la reunión o líder |
| GET | `/api/projects/<id>/agreements/` | Integrante (filtros `status`: pending/done/overdue, `responsible`) |
| GET, PATCH | `/api/agreements/<id>/` | Actualizar: responsable o líder (reasignar: líder) |

## Cobertura del MoSCoW (Laboratorio 3)

| # | Requisito | Prioridad | Dónde se ve |
|---|---|---|---|
| 1 | Autenticación, recuperación de contraseña y RBAC global | Must | Login, `/recuperar/`, roles globales |
| 2 | Permisos a nivel de proyecto | Must | Proyecto ajeno → 404 en web y API |
| 3 | CRUD de proyectos, hitos y entregables (borrado lógico) | Must | Nuevo proyecto, Editar, Editar hito, Editar entregable |
| 4 | Integrantes y responsabilidades | Must | Proyecto → Integrantes |
| 5 | Flujo de estados (tarde automático) | Must | Entregable → Flujo de estados |
| 6 | Historial de versiones (append-only, sin diff) | Must | Entregable → Versiones entregadas |
| 7 | Auditoría inmutable | Must | Proyecto → Auditoría |
| 8 | GitHub (webhook idempotente de push y PR, sincronización) | Must | Proyecto → Historial |
| 9 | Métricas (commits, PR, entregas, participación) | Must | Proyecto → Métricas por integrante |
| 10 | Dashboard por rol | Must | Inicio |
| 11 | Evaluación y retroalimentación | Must | Entregable → Aprobar / Rechazar |
| 12 | Notificaciones internas y correo | Should | Avisos |
| 13 | Reportes PDF / Excel | Should | Proyecto → Reportes |
| 14 | OAuth2 con GitHub | Should | Login → Entrar con GitHub |
| 15 | API documentada | Could | `/api/docs/` |
| 16 | Sugerencias con Gemini | Could | Entregable (con `GEMINI_API_KEY`) |
| 17 | Modo oscuro | Could | Menú lateral |
| 18 | Calendario iCal | Could | Mi perfil |
| 19–20 | App móvil, pagos | Won't (por ahora) | — |

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
| `GITHUB_TOKEN` | opcional: token de GitHub de solo lectura para sincronizar repos privados |
| `GITHUB_OAUTH_CLIENT_ID` / `GITHUB_OAUTH_CLIENT_SECRET` | opcional: activan *Entrar con GitHub* |

> ⚠️ Railway sugiere variables leídas de `.env.example` (`localhost`, `DEBUG=True`): no las agregues.
> Después de cambiar variables hay que darle a **Deploy** para que se apliquen.

> ℹ️ En el plan gratis, Postgres y Redis se duermen sin uso (Serverless obligatorio).
> La primera visita después de un rato puede fallar mientras despiertan: recarga la página.
> El pre-deploy reintenta el `migrate` hasta 6 veces por eso mismo.

**Crear el admin:** servicio `devtracker` → *Console* → `python manage.py createsuperuser`.

> ℹ️ Si la *Console* responde `python: command not found`, usa la ruta completa del entorno:
> `/app/.venv/bin/python manage.py ...`

**Sincronizar commits:** servicio `devtracker` → *Console* → `python manage.py sync_github_commits --all`.
Staging no tiene worker de Celery (el plan gratis no alcanza para otro servicio), así que el endpoint
`POST /api/projects/<id>/commits/sync/` deja la tarea en cola sin que nadie la ejecute. Para tener
worker: nuevo servicio desde el mismo repo, con las mismas variables, Start Command
`celery -A config worker --loglevel=info`, sin dominio ni health check.

## Estructura

```
config/            settings, urls, app de Celery
apps/core/         modelos base (TimeStampedModel, SoftDeleteModel), health check
apps/accounts/     User personalizado con rol global (student / evaluator / admin)
apps/projects/     Project, ProjectMembership (rol por proyecto), Milestone, Deliverable
apps/audit/        AuditLog inmutable, `log_action(...)` y endpoint de consulta
apps/integrations/ Commit, webhook de GitHub, vínculo con integrantes/entregables y sincronización (Celery)
apps/evaluations/  Evaluation inmutable (decisión, nota y retroalimentación) y endpoints de evaluación
apps/metrics/      Métricas del proyecto y por integrante
apps/web/          Interfaz web: login (también con GitHub), dashboard por rol, proyecto, entregable y perfil
apps/notifications/ Avisos en la app y por correo, recordatorios de vencimiento
apps/reports/      Reporte imprimible y exportación CSV
```

## Equipo

| Integrante | GitHub | Rol en el proyecto | Módulos a su cargo (requisitos del MoSCoW) |
|---|---|---|---|
| Eddie Man | [Eddie031-beep](https://github.com/Eddie031-beep) | Líder | Estructura base, despliegue en Railway, flujo de estados, dashboard por rol (#10), evaluación (#11), reportes (#13), documentación de la API (#15) y Could Have (#16–#18). Revisa y fusiona los PR. |
| Carlos Miranda | [Litdemonick](https://github.com/Litdemonick) | Integrante | Autenticación, roles globales y recuperación de contraseña (#1), login con GitHub (#14), webhook de GitHub y su firma (#8) |
| Harold Morales | [AtunConMayonesa06](https://github.com/AtunConMayonesa06) | Integrante | Permisos por proyecto (#2), auditoría inmutable (#7), notificaciones (#12) |
| Brayan Quintero | [Brashan09](https://github.com/Brashan09) | Integrante | CRUD de proyectos, hitos y entregables (#3), historial de versiones (#6) |
| Eliecias Cubilla | [ElieCubi](https://github.com/ElieCubi) | Integrante | Integrantes y responsabilidades (#4), sincronización con GitHub, pull requests e historial (#8), métricas por integrante (#9) |

## Cómo agregamos algo nuevo

Cada cambio sigue el mismo camino y queda registrado en DevTracker:

1. **El líder lo pide.** En el proyecto: *Nuevo hito* (la etapa, con fecha de cierre) y *Nuevo entregable* dentro
   del hito, asignado a quien lo hará. El entregable recibe un número, por ejemplo `#D16`.
2. **El integrante trabaja en su rama**, desde su propia cuenta de GitHub: `feature/D16-<tema>` a partir de
   `develop`, con `#D16` en los mensajes de commit.
3. **Abre un PR hacia `develop`** con `#D16` en el título. DevTracker lo recibe por el webhook y, si quien lo
   abre es la persona asignada, marca el entregable como *Entregado* con el enlace del PR.
4. **El evaluador revisa** en DevTracker: *Aprobar* (completo) o *Rechazar* con retroalimentación. Si lo rechaza,
   el integrante corrige en el mismo PR y cada push crea una versión nueva.
5. **Con el CI en verde, el líder fusiona** el PR. Railway despliega `develop` solo.
6. **Para publicar una versión**, PR de `develop` a `main` y una release con su etiqueta (`v1.0.0`).

Nadie sube cambios con la cuenta de otro: así las métricas y la auditoría reflejan el trabajo de cada uno.

## Plan por etapas

| Etapa | Contenido | Estado |
|---|---|---|
| **1. Seguridad y estructura base** | Auth + RBAC + recuperación de contraseña, permisos por proyecto, CRUD proyectos/hitos/entregables, asignación de integrantes, flujo de estados | ✅  Completa |
| **2. Trazabilidad y entregables** | Historial de versiones, auditoría inmutable, integración GitHub, despliegue en Railway | ✅ Completa |
| **3. Métricas y evaluación** | Métricas por integrante, dashboard por rol, evaluación | ✅ Completa |
| **4. Should / Could Have** | Docs de API, notificaciones (app y correo), reportes (CSV e imprimible), login con GitHub (OAuth2) | ✅ Completa |
| **Cierre (v1.0.0)** | Interfaz final, pull requests e historial de ramas, administración desde la web, recuperar contraseña en la web, Excel, modo oscuro, calendario iCal, Gemini opcional | ✅ Completa |
| **5. Examen semestral** | Tailwind CSS, incidencias de software, riesgos del proyecto, solicitudes de cambio de alcance, reuniones y acuerdos | ✅ Completa (PR #44–#48) |

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
| #18 | Auditoría inmutable | Harold Morales | — | #27, #28 |
| #19 | Historial de versiones de entregables | Brayan Quintero | #18 | #29 |
| #20 | Integración GitHub (parte 1): vincular repo y webhook | Carlos Miranda | #17 | #30 |
| #21 | Integración GitHub (parte 2): sincronización y vínculo con integrantes | Eliecias Cubilla | #20 | #31 |

Orden sugerido: #17 y #18 primero; #19 y #20 en paralelo; #21 al final.
#19, #20 y #21 cambian modelos compartidos (`apps/projects/models.py`, `apps/accounts/models.py`):
avisen al grupo antes de subir migraciones.

### Etapa 3: quién hace qué

| Parte | Tarea | Responsable | PR |
|---|---|---|---|
| 3.1 | Sincronización de commits sin worker (comando `sync_github_commits`) | | #33 |
| 3.2 | Métricas del proyecto y por integrante (commits, entregas, participación) | | #35 |
| 3.3 | Evaluación de entregables con nota y retroalimentación | | #35 |
| 3.4 | Dashboard por rol (estudiante, evaluador, líder, admin) | | #35 |
| 3.5 | Documentación de la API (OpenAPI + Swagger UI) | | #35 |

### Etapa 4: quién hace qué

| Parte | Tarea | Responsable | PR |
|---|---|---|---|
| 4.1 | Notificaciones en la app (avisos y contador) | | #36 |
| 4.2 | Notificaciones por correo y recordatorios de vencimiento | | #36 |
| 4.3 | Reportes: CSV e imprimible | | #36 |
| 4.4 | Iniciar sesión con GitHub (OAuth2) y perfil | | #36 |

### Etapa 5 (examen semestral): quién hace qué

| Parte | Tarea | Responsable | PR |
|---|---|---|---|
| 5.0 | Base: Tailwind CSS compilado, registro de módulos del proyecto y permisos comunes | | #44 |
| 5.1 | Gestión de incidencias de software (registro, responsable, estados, verificación y reapertura con historial) | | #45 |
| 5.2 | Gestión de riesgos (probabilidad × impacto 1–3, matriz de nivel, mitigación y estados) | | #46 |
| 5.3 | Solicitudes de cambio de alcance (propuesta, decisión del evaluador, sin tocar entregables) | | #47 |
| 5.4 | Reuniones y acuerdos (actas con participantes, acuerdos con responsable y fecha) | | #48 |

Orden de fusión: #44 primero; cada PR de la etapa 5 parte del anterior (#45 → #46 → #47 → #48).
Datos de ejemplo de los cuatro módulos: `python manage.py cargar_semestral --proyecto 1`.

### Cierre (v1.0.0)

| Tarea | Responsable | PR |
|---|---|---|
| Interfaz final, pull requests, historial y requisitos restantes del MoSCoW | | #38 |
| Arreglos de la prueba integral | | #40 |
| Versiones publicadas en `main` | | #37, #39, #41, #43 |

El detalle y los criterios de aceptación de cada tarea están en los Issues del repo.
Lee [CONTRIBUTING.md](CONTRIBUTING.md) antes de empezar.
