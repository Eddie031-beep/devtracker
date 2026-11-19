import json
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

API_URL = "https://api.github.com"
NEXT_LINK_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


def _headers(token):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "DevTracker",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get(url, token):
    with urlopen(Request(url, headers=_headers(token)), timeout=15) as response:
        return json.load(response), response.headers.get("Link") or ""


def _get_pages(url, token, max_pages):
    """Junta las páginas siguiendo el encabezado `Link` (rel="next")."""
    items = []
    for _ in range(max_pages):
        page, link = _get(url, token)
        items.extend(page)
        match = NEXT_LINK_RE.search(link)
        if not match:
            break
        url = match.group(1)
    return items


def fetch_repo_commits(repo, token="", max_pages=20, branch=""):
    """Devuelve los commits de una rama del repo (`owner/repo`; por defecto la principal), del más nuevo al más viejo.

    Pagina de 100 en 100 siguiendo el encabezado `Link`. Sin token GitHub permite 60 peticiones
    por hora y solo repos públicos; con `GITHUB_TOKEN` son 5000 y también repos privados.
    Lanza `urllib.error.HTTPError` (404 repo inexistente, 403 límite) o `URLError` (red).
    """
    url = f"{API_URL}/repos/{quote(repo)}/commits?per_page=100"
    if branch:
        url += f"&sha={quote(branch, safe='')}"
    return _get_pages(url, token, max_pages)


def fetch_default_branch(repo, token=""):
    data, _ = _get(f"{API_URL}/repos/{quote(repo)}", token)
    return data.get("default_branch") or ""


def fetch_branches(repo, token="", max_pages=1):
    """Nombres de las ramas que siguen vivas en GitHub (hasta 100)."""
    return [b["name"] for b in _get_pages(f"{API_URL}/repos/{quote(repo)}/branches?per_page=100", token, max_pages)]


def fetch_pull_requests(repo, token="", max_pages=3):
    """Pull requests abiertos y cerrados, del más nuevo al más viejo."""
    return _get_pages(f"{API_URL}/repos/{quote(repo)}/pulls?state=all&per_page=100", token, max_pages)



def fetch_repo_extras(repo, token="", max_branches=15):
    """Lo que completa el historial además de la rama principal: su nombre, las demás ramas vivas
    (solo su página más reciente, que es donde está lo nuevo) y los pull requests.

    Devuelve `(rama_principal, {rama: commits}, pull_requests)`.
    """
    default = fetch_default_branch(repo, token)
    names = [name for name in fetch_branches(repo, token) if name != default][:max_branches]
    branches = {name: fetch_repo_commits(repo, token, max_pages=1, branch=name) for name in names}
    return default, branches, fetch_pull_requests(repo, token)
