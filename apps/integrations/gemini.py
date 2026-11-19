"""Sugerencias con Gemini sobre el PR y los commits de un entregable (Could Have #16).

Es opcional: sin `GEMINI_API_KEY` no aparece nada en la interfaz. Solo se manda el texto del PR
(título, descripción, rama) y los mensajes de los commits; nunca el código ni datos de usuarios.
La sugerencia orienta al revisor; la decisión (aprobar o rechazar) la sigue tomando una persona.
"""

import json
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_COMMITS = 30


class GeminiError(Exception):
    pass


def gemini_enabled():
    return bool(settings.GEMINI_API_KEY)


def build_prompt(deliverable, pulls, commits):
    lines = [
        "Eres un asistente para el revisor de un curso de desarrollo de software. Responde en español, breve,",
        "en tres secciones con viñetas: «Qué cambia», «Riesgos o faltantes» y «Qué revisar antes de aprobar».",
        "Básate solo en la información de abajo; si algo no se puede saber, dilo. No des una nota.",
        "",
        f"Entregable: #D{deliverable.pk} {deliverable.title}",
        f"Qué se pedía: {deliverable.description or '(sin descripción)'}",
    ]
    for pr in pulls:
        lines += [
            "",
            f"Pull request #{pr.number}: {pr.title} ({pr.get_state_display()}, rama {pr.head_ref} → {pr.base_ref})",
            f"Descripción del PR: {(pr.body or '(vacía)')[:3000]}",
        ]
    if commits:
        lines += ["", "Commits vinculados:"]
        lines += [f"- {c.message.splitlines()[0][:200]}" for c in commits[:MAX_COMMITS] if c.message]
    return "\n".join(lines)


def ask_gemini(prompt):
    """Llama a la API REST de Gemini. Lanza GeminiError con un mensaje entendible si falla."""
    url = API_URL.format(model=quote(settings.GEMINI_MODEL, safe=""))
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    request = Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": settings.GEMINI_API_KEY},
    )
    try:
        with urlopen(request, timeout=30) as response:
            data = json.load(response)
    except OSError as error:  # HTTPError y URLError heredan de OSError
        code = getattr(error, "code", None)
        raise GeminiError(f"Gemini no respondió ({code or 'sin conexión'}).") from error
    try:
        return "".join(part.get("text", "") for part in data["candidates"][0]["content"]["parts"]).strip()
    except (KeyError, IndexError, TypeError) as error:
        raise GeminiError("Gemini no devolvió una sugerencia.") from error


def suggest_for_deliverable(deliverable):
    pulls = list(deliverable.pull_requests.all()[:3])
    commits = list(deliverable.commits.all()[:MAX_COMMITS])
    if not pulls and not commits:
        raise GeminiError("El entregable no tiene PR ni commits vinculados para analizar.")
    return ask_gemini(build_prompt(deliverable, pulls, commits))
