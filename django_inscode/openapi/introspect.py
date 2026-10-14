from __future__ import annotations

from typing import Any, TypeGuard, cast

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
from django_inscode.openapi.schemas import (
    paginated_response_schema,
    paginated_schema_name,
)
from django_inscode.openapi.security import security_for_view
from django_inscode.openapi.types import (
    CollectedRoute,
    HttpMethod,
    OperationSpec,
    ParameterSpec,
    RequestBodySpec,
    ResponseSpec,
)
from django_inscode.types import MethodOpenAPIMetadata, ResponseOverride
from django_inscode.views import (
    GenericModelView,
    GenericOrchestratorView,
)

_HTTP_METHODS: tuple[HttpMethod, ...] = ("get", "post", "put", "patch", "delete")
_ERROR_REF: dict[str, str] = {"$ref": "#/components/schemas/ErrorResponseSchema"}
_ERROR_DESCRIPTIONS = {
    400: "Requisição inválida.",
    401: "Não autenticado.",
    403: "Acesso negado.",
    404: "Recurso não encontrado.",
    422: "Entidade inválida.",
}


def _is_marshmallow_schema(value: object) -> TypeGuard[type[Schema]]:
    return isinstance(value, type) and issubclass(value, Schema)


def _path_has_lookup(route: CollectedRoute, lookup_field: str) -> bool:
    return any(p.name == lookup_field for p in route.path_parameters)


def _tag_from_path(path: str, strip_prefixes: tuple[str, ...] = ()) -> str:
    parts = [p for p in path.split("/") if p and not p.startswith("{")]
    skip = set(strip_prefixes)
    meaningful = [p for p in parts if p not in skip]
    return meaningful[0] if meaningful else (parts[0] if parts else "root")


def _operation_id(route: CollectedRoute, method: HttpMethod, suffix: str) -> str:
    base = route.name or route.view_class.__name__
    return f"{base}_{method}_{suffix}".lower()


def _serializer_schema(view_class: type[GenericModelView]) -> type[Schema] | None:
    serializer = view_class.serializer
    return serializer if _is_marshmallow_schema(serializer) else None


def _input_schema(view_class: type) -> type[Schema] | None:
    schema = getattr(view_class, "input_schema", None)
    return schema if _is_marshmallow_schema(schema) else None


def default_error_responses(
    *, requires_auth: bool, include_not_found: bool = False
) -> list[ResponseOverride]:
    """Respostas de erro padrão das operações geradas, no formato de `OperationOverride`."""
    codes = [
        400,
        *((401, 403) if requires_auth else ()),
        422,
        *((404,) if include_not_found else ()),
    ]
    return [
        {
            "status_code": code,
            "description": _ERROR_DESCRIPTIONS[code],
            "schema": _ERROR_REF,
        }
        for code in codes
    ]


def method_openapi_metadata(owner: type, method_name: str) -> MethodOpenAPIMetadata:
    """Metadados OpenAPI do método, herdados da base quando ele é sobrescrito sem eles."""
    for klass in owner.__mro__:
        method = vars(klass).get(method_name)
        if method is not None and hasattr(method, "metadata"):
            return method.metadata.get("openapi", {})
    return {}


def _declared_parameters(view_class: type, method_name: str) -> list[ParameterSpec]:
    return [
        ParameterSpec(**p)
        for p in method_openapi_metadata(view_class, method_name).get("parameters", [])
    ]


def _responses(
    view_class: type,
    method_name: str,
    default_schema: type[Schema] | dict[str, Any] | None,
    *,
    requires_auth: bool,
    include_not_found: bool = False,
) -> list[ResponseSpec]:
    """
    Respostas declaradas no metadata do método (sem `schema`, usa `default_schema`)
    seguidas das respostas de erro padrão que ele não declarou.
    """
    declared = [
        ResponseSpec(
            r["status_code"],
            r["description"],
            schema=r["schema"] if "schema" in r else default_schema,
        )
        for r in method_openapi_metadata(view_class, method_name).get("responses", [])
    ]
    declared_codes = {r.status_code for r in declared}
    defaults = default_error_responses(
        requires_auth=requires_auth, include_not_found=include_not_found
    )
    return [
        *declared,
        *(
            ResponseSpec(**r)
            for r in defaults
            if r["status_code"] not in declared_codes
        ),
    ]


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
    strip_prefixes: tuple[str, ...] = (),
) -> list[OperationSpec]:
    output_schema = _serializer_schema(view_class)
    if output_schema is None:
        return []

    operations: list[OperationSpec] = []
    in_schema = _input_schema(view_class)
    lookup_field = view_class.lookup_field
    is_detail = _path_has_lookup(route, lookup_field)
    tag = _tag_from_path(route.path, strip_prefixes)
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
                responses=_responses(
                    view_class, "post", output_schema, requires_auth=requires_auth
                ),
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
                    responses=_responses(
                        view_class,
                        "get",
                        output_schema,
                        requires_auth=requires_auth,
                        include_not_found=True,
                    ),
                    security=security,
                )
            )
        else:
            list_params = list(pagination_parameters())
            list_params.extend(
                filterset_to_parameters(view_class.filter_class)
            )
            paginated_name = paginated_schema_name(output_schema.__name__)
            operations.append(
                OperationSpec(
                    path=route.path,
                    method="get",
                    operation_id=_operation_id(route, "get", "list"),
                    tags=[tag],
                    summary=f"Lista {tag} com paginação.",
                    parameters=[*list_params, *_declared_parameters(view_class, "get")],
                    responses=_responses(
                        view_class,
                        "get",
                        {"$ref": f"#/components/schemas/{paginated_name}"},
                        requires_auth=requires_auth,
                    ),
                    extra_schemas=(output_schema,),
                    extra_components={
                        paginated_name: paginated_response_schema(
                            output_schema.__name__
                        )
                    },
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
                    responses=_responses(
                        view_class,
                        method,
                        output_schema,
                        requires_auth=requires_auth,
                        include_not_found=True,
                    ),
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
                responses=_responses(
                    view_class,
                    "delete",
                    output_schema,
                    requires_auth=requires_auth,
                    include_not_found=True,
                ),
                security=security,
            )
        )

    return operations


def _orchestrator_output_schema(
    view_class: type[GenericOrchestratorView],
) -> type[Schema] | None:
    serializer = getattr(view_class, "serializer", None)
    return serializer if _is_marshmallow_schema(serializer) else None


def _orchestrator_operations(
    route: CollectedRoute,
    view_class: type[GenericOrchestratorView],
    strip_prefixes: tuple[str, ...] = (),
) -> list[OperationSpec]:
    in_schema = _input_schema(view_class)
    out_schema = _orchestrator_output_schema(view_class)
    tag = _tag_from_path(route.path, strip_prefixes)
    security = security_for_view(view_class)
    requires_auth = bool(security)
    operations: list[OperationSpec] = []

    default_schema: type[Schema] | dict[str, Any] = (
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
                parameters=_declared_parameters(view_class, method),
                responses=_responses(
                    view_class,
                    "build_response",
                    default_schema,
                    requires_auth=requires_auth,
                ),
                security=security,
            )
        )
    return operations


def operations_for_route(
    route: CollectedRoute,
    strip_prefixes: tuple[str, ...] = (),
) -> list[OperationSpec]:
    """Inspeciona uma rota e devolve todas as operações OpenAPI suportadas."""
    view_class = route.view_class

    if issubclass(view_class, GenericOrchestratorView):
        return _orchestrator_operations(route, view_class, strip_prefixes)

    if issubclass(view_class, GenericModelView):
        return _model_view_operations(route, view_class, strip_prefixes)

    return []


__all__ = ["default_error_responses", "operations_for_route"]
