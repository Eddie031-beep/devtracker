import hashlib
import hmac
import re

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.projects.models import Deliverable, Project
from apps.projects.services import SUBMITTABLE_STATES, submit_deliverable

from .models import Commit, PullRequest

User = get_user_model()

# «Agrega login #D12» → entregable 12
DELIVERABLE_REF_RE = re.compile(r"#D(\d+)\b", re.IGNORECASE)
# Correos privados de GitHub: 12345+usuario@users.noreply.github.com o usuario@users.noreply.github.com
# Rama «feature/D12-login» o «d12_reportes» → entregable 12
BRANCH_REF_RE = re.compile(r"(?:^|[/_-])D(\d+)(?=$|[/_-])", re.IGNORECASE)
NULL_SHA = "0" * 40
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

    def deliverable_id_for_branch(self, branch):
        for ref in BRANCH_REF_RE.findall(branch or ""):
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
        "parents": [p["sha"] for p in item.get("parents") or [] if p.get("sha")],
    }


@transaction.atomic
def save_push_commits(project, payload):
    """Guarda los commits de un evento push. Los que ya existían se ignoran. Devuelve cuántos se crearon."""
    linker = CommitLinker(project)
    ref = payload.get("ref") or ""
    branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ""
    # El push no trae los padres: cada commit cuelga del anterior y el primero de `before`
    previous = payload.get("before") or ""
    created_count = 0
    for data in payload.get("commits") or []:
        sha = data.get("id")
        if not sha:
            continue
        fields = _parse_commit(data)
        parents = [previous] if previous and previous != NULL_SHA else []
        commit, created = Commit.objects.get_or_create(
            project=project,
            sha=sha,
            defaults={**fields, **linker.links(fields), "branch": branch[:255], "parents": parents},
        )
        if not created and not commit.parents and parents:
            commit.parents = parents
            commit.save(update_fields=["parents"])
        created_count += created
        previous = sha
    return created_count


@transaction.atomic
def save_api_commits(project, items, branch=""):
    """Guarda los commits que devuelve la API de GitHub (sincronización). Devuelve cuántos se crearon.

    A los que ya existían (p. ej. llegados por el webhook) solo les completa la rama y los padres
    reales, que la API sí trae y el push no.
    """
    linker = CommitLinker(project)
    existing = {c.sha: c for c in Commit.objects.filter(project=project).only("pk", "sha", "branch", "parents")}
    new_commits, completed = [], []
    for item in items:
        sha = item.get("sha")
        if not sha:
            continue
        fields = _parse_api_commit(item)
        if sha in existing:
            commit = existing[sha]
            if commit.pk and (commit.parents != fields["parents"] or (branch and not commit.branch)):
                commit.parents = fields["parents"]
                commit.branch = commit.branch or branch[:255]
                completed.append(commit)
            continue
        commit = Commit(project=project, sha=sha, branch=branch[:255], **fields, **linker.links(fields))
        existing[sha] = commit
        new_commits.append(commit)
    # ignore_conflicts: si el webhook guardó el mismo commit mientras sincronizábamos, no falla
    Commit.objects.bulk_create(new_commits, ignore_conflicts=True)
    Commit.objects.bulk_update(completed, ["parents", "branch"])
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


# --- Pull requests ---------------------------------------------------------------------------

# Acciones del webhook que cuentan como «el estudiante entrega su trabajo»
SUBMIT_ACTIONS = {"opened", "reopened", "ready_for_review", "synchronize"}


def _parse_pull(data):
    """PR tal como viene en el webhook `pull_request` o en `GET /repos/{owner}/{repo}/pulls`."""
    merged_at = parse_datetime(data.get("merged_at") or "")
    if merged_at:
        state = PullRequest.State.MERGED
    elif data.get("state") == "closed":
        state = PullRequest.State.CLOSED
    else:
        state = PullRequest.State.OPEN
    head = data.get("head") or {}
    base = data.get("base") or {}
    return {
        "title": (data.get("title") or "")[:500],
        "body": data.get("body") or "",
        "state": state,
        "draft": bool(data.get("draft")),
        "author_login": ((data.get("user") or {}).get("login") or "")[:100],
        "url": (data.get("html_url") or "")[:500],
        "head_ref": (head.get("ref") or "")[:255],
        "base_ref": (base.get("ref") or "")[:255],
        "head_sha": (head.get("sha") or "")[:40],
        "merge_sha": (data.get("merge_commit_sha") or "")[:40] if merged_at else "",
        "opened_at": parse_datetime(data.get("created_at") or "") or timezone.now(),
        "merged_at": merged_at,
        "closed_at": parse_datetime(data.get("closed_at") or ""),
    }


def save_pull_request(project, data, linker=None):
    """Crea o actualiza un PR por (proyecto, número): repetir el mismo evento no lo duplica."""
    number = data.get("number")
    if not number:
        return None, False
    linker = linker or CommitLinker(project)
    fields = _parse_pull(data)
    fields["author"] = linker.author_for(fields["author_login"], "")
    fields["deliverable_id"] = linker.deliverable_id_for(
        f"{fields['title']}\n{fields['body']}"
    ) or linker.deliverable_id_for_branch(fields["head_ref"])
    return PullRequest.objects.update_or_create(project=project, number=number, defaults=fields)


@transaction.atomic
def save_api_pulls(project, items):
    """Guarda los PR de la sincronización. Devuelve cuántos se crearon."""
    linker = CommitLinker(project)
    created_count = 0
    for item in items:
        _, created = save_pull_request(project, item, linker)
        created_count += created
    return created_count


def submit_from_pull_request(pull, action):
    """Si quien abre el PR es el asignado del entregable (#D<id>), lo da por entregado con el enlace del PR.

    Así el estudiante entrega desde GitHub y el revisor decide en DevTracker si está completo (aprobar)
    o no (rechazar). Si lo rechazan, el siguiente push al mismo PR vuelve a entregar una versión nueva.
    Devuelve un texto que explica qué pasó (llega a GitHub en «Recent deliveries»).
    """
    if action not in SUBMIT_ACTIONS or pull.state != PullRequest.State.OPEN:
        return ""
    if pull.draft:
        return "PR en borrador: se entregará cuando se marque como lista."
    if pull.deliverable_id is None:
        return "El PR no menciona ningún entregable (#D<id>)."
    if pull.author_id is None:
        return f"«{pull.author_login}» no es integrante del proyecto (revisa su usuario de GitHub en el perfil)."
    deliverable = pull.deliverable
    if deliverable.status not in SUBMITTABLE_STATES:
        return f"#D{deliverable.pk} ya está «{deliverable.get_status_display()}»: no se entregó de nuevo."
    try:
        submit_deliverable(
            deliverable, pull.author, url=pull.url, comment=f"PR #{pull.number}: {pull.title}"[:500]
        )
    except (PermissionDenied, ValidationError) as error:
        message = error.messages[0] if isinstance(error, ValidationError) else str(error)
        return f"#D{deliverable.pk} no se entregó: {message}"
    return f"#D{deliverable.pk} entregado con el PR #{pull.number}."
