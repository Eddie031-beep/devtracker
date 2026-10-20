import hashlib
import hmac
import re

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.projects.models import Deliverable, Project

from .models import Commit

User = get_user_model()

# «Agrega login #D12» → entregable 12
DELIVERABLE_REF_RE = re.compile(r"#D(\d+)\b", re.IGNORECASE)
# Correos privados de GitHub: 12345+usuario@users.noreply.github.com o usuario@users.noreply.github.com
NOREPLY_EMAIL_RE = re.compile(r"^(?:\d+\+)?([^@]+)@users\.noreply\.github\.com$", re.IGNORECASE)


def verify_signature(secret, body, signature_header):
    """Compara la firma `X-Hub-Signature-256` (sha256=<hex>) con el HMAC del cuerpo crudo."""
    if not secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


class CommitLinker:
    """Decide a qué integrante y a qué entregable corresponde un commit dentro de UN proyecto.

    Carga los integrantes y entregables una sola vez, para no hacer consultas por cada commit.
    """

    def __init__(self, project):
        members = User.objects.filter(memberships__project=project)
        self.by_username = {u.github_username.lower(): u for u in members if u.github_username}
        self.by_email = {u.email.lower(): u for u in members if u.email}
        # Solo entregables vivos de ESTE proyecto: «#D12» de otro proyecto no se vincula
        self.deliverable_ids = set(
            Deliverable.objects.filter(
                milestone__project=project, milestone__deleted_at__isnull=True
            ).values_list("pk", flat=True)
        )

    def author_for(self, github_username, email):
        username = github_username
        if not username and email:
            match = NOREPLY_EMAIL_RE.match(email)
            username = match.group(1) if match else ""
        if username and username.lower() in self.by_username:
            return self.by_username[username.lower()]
        return self.by_email.get((email or "").lower())

    def deliverable_id_for(self, message):
        for ref in DELIVERABLE_REF_RE.findall(message or ""):
            if int(ref) in self.deliverable_ids:
                return int(ref)
        return None

    def links(self, fields):
        return {
            "author": self.author_for(fields["github_username"], fields["author_email"]),
            "deliverable_id": self.deliverable_id_for(fields["message"]),
        }


def _parse_commit(data):
    """Commit tal como viene en el webhook `push`."""
    author = data.get("author") or {}
    return {
        "author_name": (author.get("name") or "")[:255],
        "author_email": (author.get("email") or "")[:254],
        "github_username": (author.get("username") or "")[:100],
        "message": data.get("message") or "",
        "committed_at": parse_datetime(data.get("timestamp") or "") or timezone.now(),
        "url": (data.get("url") or "")[:500],
    }


def _parse_api_commit(item):
    """Commit tal como viene en `GET /repos/{owner}/{repo}/commits` de la API REST."""
    git_author = (item.get("commit") or {}).get("author") or {}
    # `author` (la cuenta de GitHub) es null si el correo no está ligado a ninguna cuenta
    account = item.get("author") or {}
    return {
        "author_name": (git_author.get("name") or "")[:255],
        "author_email": (git_author.get("email") or "")[:254],
        "github_username": (account.get("login") or "")[:100],
        "message": (item.get("commit") or {}).get("message") or "",
        "committed_at": parse_datetime(git_author.get("date") or "") or timezone.now(),
        "url": (item.get("html_url") or "")[:500],
    }


@transaction.atomic
def save_push_commits(project, payload):
    """Guarda los commits de un evento push. Los que ya existían se ignoran. Devuelve cuántos se crearon."""
    linker = CommitLinker(project)
    created_count = 0
    for data in payload.get("commits") or []:
        sha = data.get("id")
        if not sha:
            continue
        fields = _parse_commit(data)
        _, created = Commit.objects.get_or_create(
            project=project, sha=sha, defaults={**fields, **linker.links(fields)}
        )
        created_count += created
    return created_count


@transaction.atomic
def save_api_commits(project, items):
    """Guarda los commits que devuelve la API de GitHub (sincronización). Devuelve cuántos se crearon."""
    linker = CommitLinker(project)
    existing = set(Commit.objects.filter(project=project).values_list("sha", flat=True))
    new_commits = []
    for item in items:
        sha = item.get("sha")
        if not sha or sha in existing:
            continue
        existing.add(sha)
        fields = _parse_api_commit(item)
        new_commits.append(Commit(project=project, sha=sha, **fields, **linker.links(fields)))
    # ignore_conflicts: si el webhook guardó el mismo commit mientras sincronizábamos, no falla
    Commit.objects.bulk_create(new_commits, ignore_conflicts=True)
    return len(new_commits)


@transaction.atomic
def link_commits(project):
    """Completa el integrante o entregable de los commits que quedaron sin vincular.

    Útil cuando alguien registra su `github_username` o se crea el entregable después del commit.
    Los vínculos que ya existían no se tocan. Devuelve cuántos commits se actualizaron.
    """
    linker = CommitLinker(project)
    pending = Commit.objects.filter(project=project).filter(Q(author__isnull=True) | Q(deliverable__isnull=True))
    updated = []
    for commit in pending:
        changed = False
        if commit.author_id is None:
            author = linker.author_for(commit.github_username, commit.author_email)
            if author:
                commit.author = author
                changed = True
        if commit.deliverable_id is None:
            deliverable_id = linker.deliverable_id_for(commit.message)
            if deliverable_id:
                commit.deliverable_id = deliverable_id
                changed = True
        if changed:
            updated.append(commit)
    Commit.objects.bulk_update(updated, ["author", "deliverable"])
    return len(updated)


def link_user_commits(user):
    """Vincula al usuario los commits sin autor de todos sus proyectos (tras cambiar su `github_username`)."""
    for project in Project.objects.filter(memberships__user=user).distinct():
        link_commits(project)
