"""Módulos de gestión de un proyecto (examen semestral).

Cada módulo agrega aquí una entrada y aparece solo en:
- la sección «Gestión del proyecto» de la página del proyecto, y
- las pestañas del encabezado de las páginas de los módulos (`web/_module_header.html`).
"""

from dataclasses import dataclass

from django.urls import reverse


@dataclass(frozen=True)
class ProjectModule:
    key: str  # se usa para marcar la pestaña activa
    url_name: str  # vista que recibe el id del proyecto
    label: str
    description: str


PROJECT_MODULES: list[ProjectModule] = []


def modules_for(project):
    """Módulos del proyecto con su enlace ya resuelto."""
    return [{"module": m, "url": reverse(m.url_name, args=[project.pk])} for m in PROJECT_MODULES]


def module_context(project, active, **extra):
    """Contexto común de las páginas de un módulo: proyecto, pestañas y cuál está activa."""
    return {"project": project, "modules": modules_for(project), "active_module": active, "nav": "home", **extra}
