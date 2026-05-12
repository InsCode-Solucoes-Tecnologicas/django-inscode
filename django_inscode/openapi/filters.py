from __future__ import annotations

from typing import Any

from django_filters import (
    BooleanFilter,
    CharFilter,
    DateFilter,
    DateTimeFilter,
    FilterSet,
    NumberFilter,
    UUIDFilter,
)
from django_filters.filters import Filter

from django_inscode.openapi.types import ParameterSpec


def _schema_for_filter(filter_obj: Filter) -> dict[str, Any]:
    """Resolve o JSON Schema OpenAPI mais específico para um filtro."""
    match filter_obj:
        case BooleanFilter():
            return {"type": "boolean"}
        case NumberFilter():
            return {"type": "number"}
        case DateFilter():
            return {"type": "string", "format": "date"}
        case DateTimeFilter():
            return {"type": "string", "format": "date-time"}
        case UUIDFilter():
            return {"type": "string", "format": "uuid"}
        case CharFilter():
            return {"type": "string"}
        case _:
            return {"type": "string"}


def filterset_to_parameters(
    filter_class: type[FilterSet] | None,
) -> list[ParameterSpec]:
    """Converte uma `FilterSet` em parâmetros de query OpenAPI."""
    if filter_class is None:
        return []

    parameters: list[ParameterSpec] = []
    for name, filter_obj in filter_class.base_filters.items():
        parameters.append(
            ParameterSpec(
                name=name,
                location="query",
                schema=_schema_for_filter(filter_obj),
                required=False,
                description=getattr(filter_obj, "label", None) or None,
            )
        )
    return parameters


def pagination_parameters() -> list[ParameterSpec]:
    """Parâmetros de paginação implícitos em `ViewRetrieveModelMixin.list`."""
    return [
        ParameterSpec(
            name="page",
            location="query",
            schema={"type": "integer", "minimum": 1, "default": 1},
            required=False,
            description="Número da página (paginação).",
        )
    ]


__all__ = ["filterset_to_parameters", "pagination_parameters"]
