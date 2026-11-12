"""Inicio de sesión con GitHub (OAuth2, flujo «authorization code»).

Solo entra quien ya tiene usuario en DevTracker con ese `github_username`: GitHub prueba quién es la
persona, pero no crea cuentas nuevas (los roles y proyectos los asigna el sistema, no GitHub).
"""

import json
import secrets
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

User = get_user_model()

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
SESSION_STATE = "github_oauth_state"
SESSION_NEXT = "github_oauth_next"


def is_configured():
    return bool(settings.GITHUB_OAUTH_CLIENT_ID and settings.GITHUB_OAUTH_CLIENT_SECRET)


def _callback_url(request):
    return request.build_absolute_uri(reverse("web:github_callback"))


def _fetch_json(request):
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def _exchange_code(code, redirect_uri):
    data = urlencode(
        {
            "client_id": settings.GITHUB_OAUTH_CLIENT_ID,
            "client_secret": settings.GITHUB_OAUTH_CLIENT_SECRET,
            "code": code,
            "redirect_uri": redirect_uri,
        }
    ).encode()
    payload = _fetch_json(Request(TOKEN_URL, data=data, headers={"Accept": "application/json"}))
    if "access_token" not in payload:
        raise ValueError(payload.get("error_description") or "GitHub no entregó el token.")
    return payload["access_token"]


def _github_login(token):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "DevTracker",
    }
    return _fetch_json(Request(USER_URL, headers=headers))["login"]


def github_login(request):
    if not is_configured():
        messages.error(request, "El inicio de sesión con GitHub no está configurado en este servidor.")
        return redirect("web:login")
    state = secrets.token_urlsafe(24)
    request.session[SESSION_STATE] = state
    next_url = request.GET.get("next", "")
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        request.session[SESSION_NEXT] = next_url
    params = {
        "client_id": settings.GITHUB_OAUTH_CLIENT_ID,
        "redirect_uri": _callback_url(request),
        "scope": "read:user",
        "state": state,
        "allow_signup": "false",
    }
    return redirect(f"{AUTHORIZE_URL}?{urlencode(params)}")


def github_callback(request):
    expected = request.session.pop(SESSION_STATE, None)
    next_url = request.session.pop(SESSION_NEXT, None)
    # `state` evita que otro sitio nos haga iniciar sesión con su propio código (CSRF del flujo OAuth)
    if not expected or not secrets.compare_digest(expected, request.GET.get("state", "")):
        messages.error(request, "La respuesta de GitHub no es válida. Intenta de nuevo.")
        return redirect("web:login")
    if request.GET.get("error") or not request.GET.get("code"):
        messages.error(request, "Se canceló el inicio de sesión con GitHub.")
        return redirect("web:login")

    try:
        token = _exchange_code(request.GET["code"], _callback_url(request))
        username = _github_login(token)
    except (URLError, ValueError, KeyError, TimeoutError):
        messages.error(request, "No se pudo completar el inicio de sesión con GitHub. Intenta de nuevo.")
        return redirect("web:login")

    user = User.objects.filter(github_username__iexact=username, is_active=True).first()
    if user is None:
        messages.error(
            request,
            f"La cuenta de GitHub @{username} no está vinculada a ningún usuario de DevTracker. "
            "Entra con tu contraseña y regístrala en tu perfil.",
        )
        return redirect("web:login")

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect(next_url or "web:dashboard")
