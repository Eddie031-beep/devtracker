# Cómo trabajamos

## Ramas (Git Flow simplificado)

- `main`: solo lo que se entrega. Nadie hace push directo.
- `develop`: integración. Aquí se mergean los Pull Requests.
- `feature/<issue>-<descripcion>`: una rama por tarea, creada desde `develop`.
  Ejemplo: `feature/2-permisos-proyecto`

```bash
git checkout develop && git pull
git checkout -b feature/2-permisos-proyecto
# ...trabajo...
git push -u origin feature/2-permisos-proyecto
```

Luego abre un Pull Request hacia `develop` y escribe `Closes #<issue>` en la descripción.

## Reglas

1. Cada PR necesita la revisión de al menos otro integrante y el CI en verde.
2. Los permisos se validan en el **backend** (API y vistas), no solo ocultando botones.
3. Toda regla de negocio lleva al menos una prueba (`python manage.py test`).
4. Los modelos compartidos (`apps/projects/models.py`, `apps/accounts/models.py`) se cambian
   **avisando al grupo**: si tu cambio necesita una migración, súbela en tu PR
   (`python manage.py makemigrations`).
5. Nunca se borran datos: usa el borrado lógico (`SoftDeleteModel`).
6. Commits en español, en imperativo: `Agrega endpoint de invitación a proyecto`.
