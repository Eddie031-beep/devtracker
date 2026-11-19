from urllib.error import HTTPError, URLError

from celery import shared_task
from django.conf import settings

from apps.projects.models import Project

from .github_api import fetch_repo_commits, fetch_repo_extras
from .services import link_commits, save_api_commits, save_api_pulls


@shared_task(autoretry_for=(URLError,), dont_autoretry_for=(HTTPError,), retry_backoff=True, max_retries=3)
def sync_project_commits(project_id):
    """Trae el historial del repo vinculado (commits anteriores al webhook) y vincula los pendientes.

    Se reintenta solo ante fallas de red; un 404 o 403 de GitHub no mejora reintentando.
    """
    project = Project.objects.filter(pk=project_id).first()
    if not project or not project.github_repo:
        return {"created": 0, "linked": 0, "pull_requests": 0}
    repo, token = project.github_repo, settings.GITHUB_TOKEN
    main_commits = fetch_repo_commits(repo, token)
    default, branches, pulls = fetch_repo_extras(repo, token)
    # Primero la rama principal, así cada commit queda con la primera rama donde aparece
    created = save_api_commits(project, main_commits, branch=default)
    for name, items in branches.items():
        created += save_api_commits(project, items, branch=name)
    pull_requests = save_api_pulls(project, pulls)
    linked = link_commits(project)
    return {"created": created, "linked": linked, "pull_requests": pull_requests}
