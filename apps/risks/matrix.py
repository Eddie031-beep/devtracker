"""Matriz de probabilidad e impacto (escala de 1 a 3).

nivel = probabilidad × impacto

            Impacto →   1 Bajo   2 Medio   3 Alto
Probabilidad 3 Alta        3         6         9
             2 Media       2         4         6
             1 Baja        1         2         3

- Bajo:  1–2  (se acepta y se vigila)
- Medio: 3–4  (necesita un plan de mitigación)
- Alto:  6–9  (prioridad: mitigar ya)
"""

SCALE = [(1, "Baja"), (2, "Media"), (3, "Alta")]
IMPACT_SCALE = [(1, "Bajo"), (2, "Medio"), (3, "Alto")]

LOW, MEDIUM, HIGH = "low", "medium", "high"
LEVEL_LABELS = {LOW: "Bajo", MEDIUM: "Medio", HIGH: "Alto"}
# Color de cada nivel (clases de tailwind/input.css y utilidades de Tailwind para las celdas)
LEVEL_CHIPS = {LOW: "dt-chip-green", MEDIUM: "dt-chip-amber", HIGH: "dt-chip-red"}
LEVEL_CELLS = {
    LOW: "tw-bg-green-100 tw-text-green-900 dark:tw-bg-green-950 dark:tw-text-green-200",
    MEDIUM: "tw-bg-amber-100 tw-text-amber-900 dark:tw-bg-amber-950 dark:tw-text-amber-200",
    HIGH: "tw-bg-red-100 tw-text-red-900 dark:tw-bg-red-950 dark:tw-text-red-200",
}


def score(probability, impact):
    if probability not in (1, 2, 3) or impact not in (1, 2, 3):
        raise ValueError("La probabilidad y el impacto van de 1 a 3.")
    return probability * impact


def level_for_score(value):
    if value <= 2:
        return LOW
    if value <= 4:
        return MEDIUM
    return HIGH


def level(probability, impact):
    return level_for_score(score(probability, impact))


def build_matrix(risks, selected=None):
    """Filas de la matriz (probabilidad de 3 a 1) con sus 3 celdas (impacto de 1 a 3) y los riesgos de cada una."""
    cells = {(p, i): [] for p, _ in SCALE for i, _ in IMPACT_SCALE}
    for risk in risks:
        cells[(risk.probability, risk.impact)].append(risk)
    rows = []
    for p, p_label in reversed(SCALE):
        row = []
        for i, _ in IMPACT_SCALE:
            lvl = level(p, i)
            row.append({
                "probability": p, "impact": i, "score": p * i, "level": lvl, "level_label": LEVEL_LABELS[lvl],
                "css": LEVEL_CELLS[lvl], "risks": cells[(p, i)], "selected": selected == (p, i),
            })
        rows.append({"probability": p, "label": p_label, "cells": row})
    return {"rows": rows, "impacts": IMPACT_SCALE}
