from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from django.views import View
from marshmallow import Schema

HttpMethod = Literal["get", "post", "put", "patch", "delete"]

ParameterLocation = Literal["path", "query", "header", "cookie"]


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    """Um parâmetro OpenAPI (path, query, etc.)."""

    name: str
    location: ParameterLocation
    schema: dict[str, Any]
    required: bool = False
    description: str | None = None

    def to_openapi(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "in": self.location,
            "required": self.required,
            "schema": self.schema,
        }
        if self.description:
            out["description"] = self.description
        return out


@dataclass(frozen=True, slots=True)
class ResponseSpec:
    """Uma resposta de uma operação OpenAPI."""

    status_code: int
    description: str
    schema: type[Schema] | dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class RequestBodySpec:
    """Corpo de uma requisição. `partial=True` traduz pra Schema(partial=True)."""

    schema: type[Schema]
    partial: bool = False
    content_type: str = "application/json"
    required: bool = True


@dataclass(slots=True)
class OperationSpec:
    """Descreve uma única operação (path + método HTTP)."""

    path: str
    method: HttpMethod
    operation_id: str
    tags: list[str] = field(default_factory=list)
    summary: str | None = None
    description: str | None = None
    parameters: list[ParameterSpec] = field(default_factory=list)
    request_body: RequestBodySpec | None = None
    responses: list[ResponseSpec] = field(default_factory=list)
    extra_schemas: tuple[type[Schema], ...] = ()
    security: list[dict[str, list[str]]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CollectedRoute:
    """Uma rota descoberta na URLConf."""

    path: str
    path_parameters: tuple[ParameterSpec, ...]
    view_class: type[View]
    name: str | None = None


__all__ = [
    "HttpMethod",
    "ParameterLocation",
    "ParameterSpec",
    "ResponseSpec",
    "RequestBodySpec",
    "OperationSpec",
    "CollectedRoute",
]
