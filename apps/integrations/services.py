import hashlib
import hmac

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Commit


def verify_signature(secret, body, signature_header):
    """Compara la firma `X-Hub-Signature-256` (sha256=<hex>) con el HMAC del cuerpo crudo."""
    if not secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def _parse_commit(data):
    author = data.get("author") or {}
    return {
        "author_name": (author.get("name") or "")[:255],
        "author_email": (author.get("email") or "")[:254],
        "github_username": (author.get("username") or "")[:100],
        "message": data.get("message") or "",
        "committed_at": parse_datetime(data.get("timestamp") or "") or timezone.now(),
        "url": (data.get("url") or "")[:500],
    }


@transaction.atomic
def save_push_commits(project, payload):
    """Guarda los commits de un evento push. Los que ya existían se ignoran. Devuelve cuántos se crearon."""
    created_count = 0
    for data in payload.get("commits") or []:
        sha = data.get("id")
        if not sha:
            continue
        _, created = Commit.objects.get_or_create(project=project, sha=sha, defaults=_parse_commit(data))
        created_count += created
    return created_count
