from __future__ import annotations

from collections import defaultdict
from typing import Any, cast

from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from marshmallow import Schema

from django_inscode.openapi.collector import collect_routes
from django_inscode.openapi.introspect import operations_for_route
from django_inscode.openapi.schemas import ErrorResponseSchema, PaginationSchema
from django_inscode.openapi.security import registered_schemes
from django_inscode.openapi.types import (
    CollectedRoute,
    OperationSpec,
    ParameterSpec,
    ResponseSpec,
)

_OPENAPI_VERSION = "3.0.3"


def _schema_ref(schema_class: type[Schema]) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{schema_class.__name__}"}


def _response_to_openapi(response: ResponseSpec) -> dict[str, Any]:
    entry: dict[str, Any] = {"description": response.description}
    schema = response.schema
    if schema is None:
        return entry
    if isinstance(schema, type) and issubclass(schema, Schema):
        media = {"schema": _schema_ref(schema)}
    else:
        media = {"schema": cast(dict[str, Any], schema)}
    entry["content"] = {"application/json": media}
    return entry


def _operation_to_openapi(
    op: OperationSpec,
    path_parameters: tuple[ParameterSpec, ...],
) -> dict[str, Any]:
    parameters = [p.to_openapi() for p in (*path_parameters, *op.parameters)]
    out: dict[str, Any] = {
        "operationId": op.operation_id,
        "tags": op.tags,
        "responses": {
            str(r.status_code): _response_to_openapi(r) for r in op.responses
        },
    }
    if op.summary:
        out["summary"] = op.summary
    if op.description:
        out["description"] = op.description
    if parameters:
        out["parameters"] = parameters
    if op.security:
        out["security"] = list(op.security)
    if op.request_body is not None:
        body_entry: dict[str, Any] = {
            "required": op.request_body.required,
            "content": {
                op.request_body.content_type: {
                    "schema": _schema_ref(op.request_body.schema)
                }
            },
        }
        if op.request_body.partial:
            body_entry["description"] = "PATCH: todos os campos são opcionais."
        out["requestBody"] = body_entry
    return out


def _collect_referenced_schemas(
    operations: list[OperationSpec],
) -> dict[str, type[Schema]]:
    found: dict[str, type[Schema]] = {}
    for op in operations:
        if op.request_body is not None:
            schema = op.request_body.schema
            found[schema.__name__] = schema
        for response in op.responses:
            schema = response.schema
            if isinstance(schema, type) and issubclass(schema, Schema):
                found[schema.__name__] = schema
        for extra in op.extra_schemas:
            found[extra.__name__] = extra
    return found


def build_spec(
    *,
    title: str,
    version: str,
    description: str | None = None,
    urlconf: str | None = None,
) -> APISpec:
    """
    Constrói uma `APISpec` populada a partir da URLConf do projeto.

    Args:
        title: título da API.
        version: versão da API.
        description: descrição opcional.
        urlconf: módulo URLConf alternativo (default: settings.ROOT_URLCONF).
    """
    spec_kwargs: dict[str, Any] = {
        "title": title,
        "version": version,
        "openapi_version": _OPENAPI_VERSION,
        "plugins": [MarshmallowPlugin()],
    }
    if description:
        spec_kwargs["info"] = {"description": description}

    spec = APISpec(**spec_kwargs)
    spec.components.schema("Pagination", schema=PaginationSchema)
    spec.components.schema("ErrorResponse", schema=ErrorResponseSchema)

    for name, scheme in registered_schemes().items():
        spec.components.security_scheme(name, scheme)

    routes: list[CollectedRoute] = collect_routes(urlconf)
    operations_by_path: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    all_operations: list[OperationSpec] = []
    path_params_by_path: dict[str, tuple[ParameterSpec, ...]] = {}

    for route in routes:
        ops = operations_for_route(route)
        if not ops:
            continue
        path_params_by_path.setdefault(route.path, route.path_parameters)
        all_operations.extend(ops)
        for op in ops:
            operations_by_path[op.path][op.method] = _operation_to_openapi(
                op, path_params_by_path[op.path]
            )

    for name, schema_class in _collect_referenced_schemas(all_operations).items():
        if name in ("Pagination", "ErrorResponse"):
            continue
        spec.components.schema(name, schema=schema_class)

    for path, operations in operations_by_path.items():
        spec.path(path=path, operations=operations)

    return spec


def generate_openapi(
    *,
    title: str,
    version: str,
    description: str | None = None,
    urlconf: str | None = None,
) -> dict[str, Any]:
    """Atalho que devolve diretamente o dict OpenAPI 3."""
    return build_spec(
        title=title,
        version=version,
        description=description,
        urlconf=urlconf,
    ).to_dict()


__all__ = ["build_spec", "generate_openapi"]
