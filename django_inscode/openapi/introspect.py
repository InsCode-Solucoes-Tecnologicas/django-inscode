from __future__ import annotations

from typing import Any, cast

from marshmallow import Schema

from django_inscode.mixins import (
    ViewCreateModelMixin,
    ViewDeleteModelMixin,
    ViewRetrieveModelMixin,
    ViewUpdateModelMixin,
)
from django_inscode.openapi.filters import (
    filterset_to_parameters,
    pagination_parameters,
)
from django_inscode.openapi.security import security_for_view
from django_inscode.openapi.types import (
    CollectedRoute,
    HttpMethod,
    OperationSpec,
    RequestBodySpec,
    ResponseSpec,
)
from django_inscode.views import (
    GenericModelView,
    GenericOrchestratorView,
)

_HTTP_METHODS: tuple[HttpMethod, ...] = ("get", "post", "put", "patch", "delete")
_ERROR_REF: dict[str, str] = {"$ref": "#/components/schemas/ErrorResponse"}
_BAD_REQUEST = ResponseSpec(400, "Requisição inválida.", schema=_ERROR_REF)
_UNAUTHORIZED = ResponseSpec(401, "Não autenticado.", schema=_ERROR_REF)
_FORBIDDEN = ResponseSpec(403, "Acesso negado.", schema=_ERROR_REF)
_UNPROCESSABLE = ResponseSpec(422, "Entidade inválida.", schema=_ERROR_REF)
_NOT_FOUND_RESPONSE = ResponseSpec(404, "Recurso não encontrado.", schema=_ERROR_REF)


def _is_marshmallow_schema(value: object) -> bool:
    return isinstance(value, type) and issubclass(value, Schema)


def _path_has_lookup(route: CollectedRoute, lookup_field: str) -> bool:
    return any(p.name == lookup_field for p in route.path_parameters)


def _tag_from_path(path: str) -> str:
    parts = [p for p in path.split("/") if p and not p.startswith("{")]
    return parts[0] if parts else "root"


def _operation_id(route: CollectedRoute, method: HttpMethod, suffix: str) -> str:
    base = route.name or route.view_class.__name__
    return f"{base}_{method}_{suffix}".lower()


def _serializer_schema(view_class: type[GenericModelView]) -> type[Schema] | None:
    serializer = view_class.serializer
    return cast(type[Schema], serializer) if _is_marshmallow_schema(serializer) else None


def _input_schema(view_class: type) -> type[Schema] | None:
    schema = getattr(view_class, "input_schema", None)
    return cast(type[Schema], schema) if _is_marshmallow_schema(schema) else None


def _build_default_responses(
    *, requires_auth: bool, include_not_found: bool = False
) -> list[ResponseSpec]:
    responses: list[ResponseSpec] = [_BAD_REQUEST]
    if requires_auth:
        responses.extend((_UNAUTHORIZED, _FORBIDDEN))
    responses.append(_UNPROCESSABLE)
    if include_not_found:
        responses.append(_NOT_FOUND_RESPONSE)
    return responses


def _is_user_defined_method(view_class: type, method: HttpMethod) -> bool:
    """True se `method` foi definido em uma subclasse de `GenericOrchestratorView`."""
    for klass in view_class.__mro__:
        if klass is GenericOrchestratorView:
            return False
        if method in vars(klass):
            return True
    return False


def _model_view_operations(
    route: CollectedRoute,
    view_class: type[GenericModelView],
) -> list[OperationSpec]:
    output_schema = _serializer_schema(view_class)
    if output_schema is None:
        return []

    operations: list[OperationSpec] = []
    in_schema = _input_schema(view_class)
    lookup_field = view_class.lookup_field
    is_detail = _path_has_lookup(route, lookup_field)
    tag = _tag_from_path(route.path)
    security = security_for_view(view_class)
    requires_auth = bool(security)

    if not is_detail and issubclass(view_class, ViewCreateModelMixin):
        operations.append(
            OperationSpec(
                path=route.path,
                method="post",
                operation_id=_operation_id(route, "post", "create"),
                tags=[tag],
                summary=f"Cria um novo {tag}.",
                request_body=(
                    RequestBodySpec(schema=in_schema) if in_schema else None
                ),
                responses=[
                    ResponseSpec(201, "Criado.", schema=output_schema),
                    *_build_default_responses(requires_auth=requires_auth),
                ],
                security=security,
            )
        )

    if issubclass(view_class, ViewRetrieveModelMixin):
        if is_detail:
            operations.append(
                OperationSpec(
                    path=route.path,
                    method="get",
                    operation_id=_operation_id(route, "get", "retrieve"),
                    tags=[tag],
                    summary=f"Recupera um {tag} pelo identificador.",
                    responses=[
                        ResponseSpec(200, "OK.", schema=output_schema),
                        *_build_default_responses(
                            requires_auth=requires_auth, include_not_found=True
                        ),
                    ],
                    security=security,
                )
            )
        else:
            list_params = list(pagination_parameters())
            list_params.extend(
                filterset_to_parameters(view_class.filter_class)
            )
            paginated_schema: dict[str, object] = {
                "type": "object",
                "properties": {
                    "pagination": {"$ref": "#/components/schemas/Pagination"},
                    "results": {
                        "type": "array",
                        "items": {
                            "$ref": f"#/components/schemas/{output_schema.__name__}"
                        },
                    },
                },
                "required": ["pagination", "results"],
            }
            operations.append(
                OperationSpec(
                    path=route.path,
                    method="get",
                    operation_id=_operation_id(route, "get", "list"),
                    tags=[tag],
                    summary=f"Lista {tag} com paginação.",
                    parameters=list_params,
                    responses=[
                        ResponseSpec(200, "OK.", schema=paginated_schema),
                        *_build_default_responses(requires_auth=requires_auth),
                    ],
                    extra_schemas=(output_schema,),
                    security=security,
                )
            )

    if is_detail and issubclass(view_class, ViewUpdateModelMixin):
        for method, partial, label in (
            ("patch", True, "atualiza parcialmente"),
            ("put", False, "atualiza"),
        ):
            operations.append(
                OperationSpec(
                    path=route.path,
                    method=cast(HttpMethod, method),
                    operation_id=_operation_id(route, cast(HttpMethod, method), method),
                    tags=[tag],
                    summary=f"{label.capitalize()} um {tag}.",
                    request_body=(
                        RequestBodySpec(schema=in_schema, partial=partial)
                        if in_schema
                        else None
                    ),
                    responses=[
                        ResponseSpec(200, "OK.", schema=output_schema),
                        *_build_default_responses(
                            requires_auth=requires_auth, include_not_found=True
                        ),
                    ],
                    security=security,
                )
            )

    if is_detail and issubclass(view_class, ViewDeleteModelMixin):
        operations.append(
            OperationSpec(
                path=route.path,
                method="delete",
                operation_id=_operation_id(route, "delete", "delete"),
                tags=[tag],
                summary=f"Remove um {tag}.",
                responses=[
                    ResponseSpec(204, "Sem conteúdo."),
                    *_build_default_responses(
                        requires_auth=requires_auth, include_not_found=True
                    ),
                ],
                security=security,
            )
        )

    return operations


def _orchestrator_output_schema(
    view_class: type[GenericOrchestratorView],
) -> type[Schema] | None:
    serializer = getattr(view_class, "serializer", None)
    return cast(type[Schema], serializer) if _is_marshmallow_schema(serializer) else None


def _orchestrator_operations(
    route: CollectedRoute,
    view_class: type[GenericOrchestratorView],
) -> list[OperationSpec]:
    in_schema = _input_schema(view_class)
    out_schema = _orchestrator_output_schema(view_class)
    tag = _tag_from_path(route.path)
    security = security_for_view(view_class)
    requires_auth = bool(security)
    operations: list[OperationSpec] = []

    response_schema: type[Schema] | dict[str, Any] = (
        out_schema
        if out_schema is not None
        else {"type": "object", "additionalProperties": True}
    )

    for method in _HTTP_METHODS:
        if not _is_user_defined_method(view_class, method):
            continue
        operations.append(
            OperationSpec(
                path=route.path,
                method=method,
                operation_id=_operation_id(route, method, "execute"),
                tags=[tag],
                summary=view_class.__doc__.strip().splitlines()[0]
                if view_class.__doc__
                else f"Executa {view_class.__name__}.",
                request_body=(
                    RequestBodySpec(schema=in_schema)
                    if in_schema and method != "get"
                    else None
                ),
                responses=[
                    ResponseSpec(200, "OK.", schema=response_schema),
                    *_build_default_responses(requires_auth=requires_auth),
                ],
                security=security,
            )
        )
    return operations


def operations_for_route(route: CollectedRoute) -> list[OperationSpec]:
    """Inspeciona uma rota e devolve todas as operações OpenAPI suportadas."""
    view_class = route.view_class

    if issubclass(view_class, GenericOrchestratorView):
        return _orchestrator_operations(route, view_class)

    if issubclass(view_class, GenericModelView):
        return _model_view_operations(route, view_class)

    return []


__all__ = ["operations_for_route"]
