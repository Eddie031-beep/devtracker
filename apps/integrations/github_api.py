import json
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

API_URL = "https://api.github.com"
NEXT_LINK_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


def fetch_repo_commits(repo, token="", max_pages=20):
    """Devuelve los commits de la rama principal del repo (`owner/repo`), del más nuevo al más viejo.

    Pagina de 100 en 100 siguiendo el encabezado `Link`. Sin token GitHub permite 60 peticiones
    por hora y solo repos públicos; con `GITHUB_TOKEN` son 5000 y también repos privados.
    Lanza `urllib.error.HTTPError` (404 repo inexistente, 403 límite) o `URLError` (red).
    """
    url = f"{API_URL}/repos/{quote(repo)}/commits?per_page=100"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "DevTracker",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    commits = []
    for _ in range(max_pages):
        with urlopen(Request(url, headers=headers), timeout=15) as response:
            commits.extend(json.load(response))
            match = NEXT_LINK_RE.search(response.headers.get("Link") or "")
        if not match:
            break
        url = match.group(1)
    return commits
