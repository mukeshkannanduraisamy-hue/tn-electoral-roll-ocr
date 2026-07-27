"""Document template discovery."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.core import TemplateInfo
from ..templates import registry

router = APIRouter()


@router.get("", response_model=list[TemplateInfo])
def list_templates() -> list[TemplateInfo]:
    return registry.describe()


@router.get("/{template_id}", response_model=TemplateInfo)
def get_template(template_id: str) -> TemplateInfo:
    try:
        template = registry.get(template_id)
    except KeyError as exc:
        raise HTTPException(404, "Template not found") from exc

    return TemplateInfo(
        id=template.id,
        name=template.name,
        description=template.description,
        columns=template.columns(),
        languages=list(template.languages),
    )
