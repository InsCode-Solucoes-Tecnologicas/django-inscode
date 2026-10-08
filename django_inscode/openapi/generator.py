from __future__ import annotations

from collections import defaultdict
from typing import Any, cast

from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from apispec.ext.marshmallow.common import (
    MODIFIERS,
    make_schema_key,
    resolve_schema_instance,
)
from marshmallow import Schema, fields, validate

from django_inscode.openapi.collector import collect_routes
from django_inscode.openapi.introspect import operations_for_route
from django_inscode.openapi.schemas import ErrorResponseSchema, PaginationSchema
from django_inscode.openapi.security import (
    SecurityRequirement,
    default_security,
    registered_schemes,
)
from django_inscode.openapi.types import (
    CollectedRoute,
    OperationSpec,
    ParameterSpec,
    ResponseSpec,
)

_OPENAPI_VERSION = "3.1.0"


def _sort_unordered_choices(
    self: Any, field: fields.Field, ret: dict[str, Any], **kwargs: Any
) -> dict[str, Any]:
    """
    Ordena o `enum` de campos cujo `OneOf` recebe `set`/`frozenset`.

    A ordem de iteração de um set de strings muda a cada processo, o que torna
    a spec instável entre gerações. Listas e tuplas mantêm a ordem declarada.
    """
    if "enum" not in ret:
        return {}
    has_unordered = any(
        isinstance(v, validate.OneOf) and isinstance(v.choices, (set, frozenset))
        for v in field.validators
    )
    if not has_unordered:
        return {}
    return {"enum": sorted(ret["enum"], key=lambda v: (v is None, str(v)))}


class _SchemaNamer:
    """
    Nomeia componentes pelo nome da classe (o resolver padrão do apispec remove o
    `Schema`).

    O nome da classe fica com a classe sem `only`/`exclude`/etc. Projeções e
    classes homônimas de outros módulos ganham sufixo numérico, para que fiquem
    visíveis na spec.
    """

    def __init__(self) -> None:
        self._names: dict[tuple[Any, ...], str] = {}
        self._taken: set[str] = set()

    def __call__(self, schema: type[Schema] | Schema) -> str:
        instance = resolve_schema_instance(schema)
        key = make_schema_key(instance)
        if key in self._names:
            return self._names[key]

        base = type(instance).__name__
        is_projection = any(getattr(instance, m) for m in MODIFIERS)
        name = base
        suffix = 1
        while is_projection or name in self._taken:
            name = f"{base}{suffix}"
            suffix += 1
            is_projection = False

        self._names[key] = name
        self._taken.add(name)
        return name


_JSON_TYPES: tuple[tuple[type, str], ...] = (
    (bool, "boolean"),
    (int, "integer"),
    (float, "number"),
    (str, "string"),
)


def _describe_constant(
    self: Any, field: fields.Field, ret: dict[str, Any], **kwargs: Any
) -> dict[str, Any]:
    """O apispec não descreve `fields.Constant`; documenta o valor fixo como `const`."""
    if not isinstance(field, fields.Constant):
        return {}
    described: dict[str, Any] = {"const": field.constant}
    for python_type, json_type in _JSON_TYPES:
        if isinstance(field.constant, python_type):
            described["type"] = json_type
            break
    return described


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
    global_security: list[SecurityRequirement],
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
    if op.security != global_security:
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
    strip_path_prefixes: tuple[str, ...] = (),
) -> APISpec:
    """
    Constrói uma `APISpec` populada a partir da URLConf do projeto.

    Args:
        title: título da API.
        version: versão da API.
        description: descrição opcional.
        urlconf: módulo URLConf alternativo (default: settings.ROOT_URLCONF).
        strip_path_prefixes: segmentos de path a ignorar ao derivar a tag de
            agrupamento (ex.: `("api", "v1")` faz `/api/v1/processo-habilitacao/`
            ser agrupado como `processo-habilitacao`).
    """
    namer = _SchemaNamer()
    marshmallow_plugin = MarshmallowPlugin(schema_name_resolver=namer)
    spec_kwargs: dict[str, Any] = {
        "title": title,
        "version": version,
        "openapi_version": _OPENAPI_VERSION,
        "plugins": [marshmallow_plugin],
    }
    if description:
        spec_kwargs["info"] = {"description": description}

    global_security = default_security()
    if global_security:
        spec_kwargs["security"] = global_security

    spec = APISpec(**spec_kwargs)
    assert marshmallow_plugin.converter is not None
    marshmallow_plugin.converter.add_attribute_function(_sort_unordered_choices)
    marshmallow_plugin.converter.add_attribute_function(_describe_constant)
    for base_schema in (PaginationSchema, ErrorResponseSchema):
        spec.components.schema(namer(base_schema), schema=base_schema)

    for name, scheme in registered_schemes().items():
        spec.components.security_scheme(name, scheme)

    routes: list[CollectedRoute] = collect_routes(urlconf)
    operations_by_path: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    all_operations: list[OperationSpec] = []
    path_params_by_path: dict[str, tuple[ParameterSpec, ...]] = {}

    for route in routes:
        ops = operations_for_route(route, strip_path_prefixes)
        if not ops:
            continue
        path_params_by_path.setdefault(route.path, route.path_parameters)
        all_operations.extend(ops)
        for op in ops:
            operations_by_path[op.path][op.method] = _operation_to_openapi(
                op, path_params_by_path[op.path], global_security
            )

    referenced = _collect_referenced_schemas(all_operations)
    # As operações referenciam esses schemas pelo nome da classe: reservá-los antes
    # de registrar qualquer um impede que um aninhado homônimo tome o nome.
    for name, schema_class in referenced.items():
        if namer(schema_class) != name:
            raise ValueError(
                f"Dois schemas referenciados por operações se chamam {name}; "
                "renomeie um deles."
            )
    for name, schema_class in referenced.items():
        if name not in spec.components.schemas:
            spec.components.schema(name, schema=schema_class)

    extra_components = {
        name: component
        for op in all_operations
        for name, component in op.extra_components.items()
    }
    for name, component in extra_components.items():
        spec.components.schema(name, component=component)

    for path, operations in operations_by_path.items():
        spec.path(path=path, operations=operations)

    return spec


def generate_openapi(
    *,
    title: str,
    version: str,
    description: str | None = None,
    urlconf: str | None = None,
    strip_path_prefixes: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Atalho que devolve diretamente o dict OpenAPI 3."""
    return build_spec(
        title=title,
        version=version,
        description=description,
        urlconf=urlconf,
        strip_path_prefixes=strip_path_prefixes,
    ).to_dict()


__all__ = ["build_spec", "generate_openapi"]
