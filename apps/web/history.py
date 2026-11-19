"""Grafo del historial (estilo GitKraken, versión simple) dibujado en el servidor como SVG.

Cada commit es una fila; cada rama ocupa un carril. Se recorre del más nuevo al más viejo:
un carril «espera» al siguiente padre; cuando llega ese commit, los carriles que lo esperaban
se juntan en su nodo (así se ven las fusiones) y sus padres siguen hacia abajo.
"""

import heapq

ROW_H = 44
LANE_W = 18
PAD = 14
COLORS = ["#2747C8", "#3E9B5F", "#E08A2E", "#9B4DCA", "#D2465A", "#1C9AAA", "#8A6D3B"]


def _x(lane):
    return PAD + lane * LANE_W


def _path(x1, y1, x2, y2):
    if x1 == x2:
        return f"M{x1} {y1}L{x2} {y2}"
    mid = (y1 + y2) / 2
    return f"M{x1} {y1}C{x1} {mid} {x2} {mid} {x2} {y2}"


def _date_order(commits, parents):
    """Del más nuevo al más viejo, pero ningún padre aparece antes que sus hijos (como `git log --date-order`)."""
    pending_children = {c.sha: 0 for c in commits}
    for c in commits:
        for p in parents[c.sha]:
            pending_children[p] += 1
    by_sha = {c.sha: c for c in commits}
    ready = [(-c.committed_at.timestamp(), i, c.sha) for i, c in enumerate(commits) if pending_children[c.sha] == 0]
    heapq.heapify(ready)
    index = {c.sha: i for i, c in enumerate(commits)}
    ordered = []
    while ready:
        _, _, sha = heapq.heappop(ready)
        ordered.append(by_sha[sha])
        for p in parents[sha]:
            pending_children[p] -= 1
            if pending_children[p] == 0:
                heapq.heappush(ready, (-by_sha[p].committed_at.timestamp(), index[p], p))
    return ordered


def build_graph(commits, pulls=(), highlight=None):
    """Devuelve las filas (commit + posición + etiquetas) y el SVG ya calculado para la plantilla.

    `highlight(commit)` decide qué filas quedan resaltadas (las demás se atenúan, sin romper el grafo).
    """
    commits = list(commits)
    known = {c.sha for c in commits}
    parents = {c.sha: [p for p in (c.parents or []) if p in known] for c in commits}
    # El push no trae el segundo padre de una fusión; el PR fusionado sí dice qué rama entró
    for pr in pulls:
        if pr.merge_sha in known and pr.head_sha in known and pr.head_sha not in parents[pr.merge_sha]:
            if pr.head_sha != pr.merge_sha:
                parents[pr.merge_sha].append(pr.head_sha)

    pr_tags = {}
    for pr in pulls:
        sha = pr.merge_sha if pr.state == pr.State.MERGED else pr.head_sha
        if sha in known:
            pr_tags.setdefault(sha, []).append(pr)

    lanes, rows, edges, nodes = [], [], [], []
    seen_branches = set()
    width_lanes = 1
    for i, commit in enumerate(_date_order(commits, parents)):
        y0, ym, y1 = i * ROW_H, i * ROW_H + ROW_H // 2, (i + 1) * ROW_H
        before = list(lanes)
        hits = [j for j, sha in enumerate(lanes) if sha == commit.sha]
        if hits:
            col = hits[0]
            for j in hits[1:]:
                lanes[j] = None
        else:
            col = lanes.index(None) if None in lanes else len(lanes)
            if col == len(lanes):
                lanes.append(None)

        own = parents[commit.sha]
        lanes[col] = own[0] if own else None
        targets = [col] if own else []
        for p in own[1:]:
            if p in lanes:
                k = lanes.index(p)
            else:
                k = lanes.index(None) if None in lanes else len(lanes)
                if k == len(lanes):
                    lanes.append(None)
                lanes[k] = p
            targets.append(k)
        while lanes and lanes[-1] is None:
            lanes.pop()
        width_lanes = max(width_lanes, len(before), len(lanes), col + 1)

        for j, sha in enumerate(before):
            if sha is None:
                continue
            color = COLORS[j % len(COLORS)]
            if sha == commit.sha:
                edges.append((_path(_x(j), y0, _x(col), ym), color))
            else:
                edges.append((_path(_x(j), y0, _x(j), y1), color))
        for k in targets:
            edges.append((_path(_x(col), ym, _x(k), y1), COLORS[k % len(COLORS)]))

        branch_tag = ""
        if commit.branch and commit.branch not in seen_branches:
            seen_branches.add(commit.branch)
            branch_tag = commit.branch
        dim = highlight is not None and not highlight(commit)
        nodes.append({"x": _x(col), "y": ym, "color": COLORS[col % len(COLORS)], "merge": len(own) > 1, "dim": dim})
        rows.append(
            {
                "commit": commit,
                "branch": branch_tag,
                "pulls": pr_tags.get(commit.sha, []),
                "merge": len(own) > 1,
                "color": COLORS[col % len(COLORS)],
                "dim": dim,
            }
        )

    width = PAD * 2 + (width_lanes - 1) * LANE_W
    return {
        "rows": rows,
        "edges": [{"d": d, "color": color} for d, color in edges],
        "nodes": nodes,
        "width": width,
        "height": len(rows) * ROW_H,
        "row_h": ROW_H,
    }
