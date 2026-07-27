"""Template registry and auto-detection.

Add a new document type by writing a module exposing a `TEMPLATE` object that
satisfies `base.DocumentTemplate`, then registering it here.
"""

from __future__ import annotations

import logging

from ..schemas.core import OcrLine, TemplateInfo
from .base import DocumentTemplate
from .electoral_roll_ta import TEMPLATE as ELECTORAL_ROLL_TA
from .generic import TEMPLATE as GENERIC

logger = logging.getLogger(__name__)

# Order matters only for tie-breaking; detection scores decide the winner.
_TEMPLATES: list[DocumentTemplate] = [
    ELECTORAL_ROLL_TA,
    GENERIC,
]

_BY_ID: dict[str, DocumentTemplate] = {t.id: t for t in _TEMPLATES}

# Below this score we don't trust a specific template and use the generic one.
DETECTION_FLOOR = 0.45


def all_templates() -> list[DocumentTemplate]:
    return list(_TEMPLATES)


def get(template_id: str) -> DocumentTemplate:
    if template_id not in _BY_ID:
        raise KeyError(f"Unknown template: {template_id}")
    return _BY_ID[template_id]


def get_or_generic(template_id: str | None) -> DocumentTemplate:
    if not template_id:
        return GENERIC
    return _BY_ID.get(template_id, GENERIC)


def describe() -> list[TemplateInfo]:
    return [
        TemplateInfo(
            id=t.id,
            name=t.name,
            description=t.description,
            columns=t.columns(),
            languages=list(t.languages),
        )
        for t in _TEMPLATES
    ]


def detect(
    lines: list[OcrLine], page_size: tuple[int, int]
) -> tuple[DocumentTemplate, float]:
    """Pick the best-fitting template for a page.

    Returns (template, confidence). Falls back to the generic template when
    no specific template clears `DETECTION_FLOOR`.
    """
    scored: list[tuple[float, DocumentTemplate]] = []
    for template in _TEMPLATES:
        if template.id == GENERIC.id:
            continue
        try:
            score = float(template.detect(lines, page_size))
        except Exception as exc:  # noqa: BLE001 - a broken template must not
            logger.warning("Template %s failed detection: %s", template.id, exc)
            continue
        scored.append((score, template))

    if scored:
        scored.sort(key=lambda pair: pair[0], reverse=True)
        best_score, best_template = scored[0]
        if best_score >= DETECTION_FLOOR:
            return best_template, round(best_score, 4)

    return GENERIC, 0.05
