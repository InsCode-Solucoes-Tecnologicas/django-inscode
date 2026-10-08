from __future__ import annotations

import copy
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
_SCHEMA_REF_PREFIX = "#/components/schemas/"


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
        self.instances: dict[str, Schema] = {}

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
        self.instances[name] = instance
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
    return {"$ref": f"{_SCHEMA_REF_PREFIX}{schema_class.__name__}"}


def _partial_name(name: str) -> str:
    return f"Partial{name}"


def _non_updatable_properties(schema_class: type[Schema]) -> frozenset[str]:
    schema = resolve_schema_instance(schema_class)
    return frozenset(
        field.data_key or field_name
        for field_name, field in schema.fields.items()
        if not field.metadata.get("updatable", True)
    )


def _point_refs_to_partial(node: Any) -> list[str]:
    """Troca cada `$ref` de schema por sua variante parcial; devolve os nomes trocados."""
    found: list[str] = []
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(_SCHEMA_REF_PREFIX):
            name = ref.removeprefix(_SCHEMA_REF_PREFIX)
            node["$ref"] = f"{_SCHEMA_REF_PREFIX}{_partial_name(name)}"
            found.append(name)
        for value in node.values():
            found.extend(_point_refs_to_partial(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_point_refs_to_partial(item))
    return found


def _referenced_names(node: Any) -> list[str]:
    if isinstance(node, dict):
        ref = node.get("$ref")
        names = (
            [ref.removeprefix(_SCHEMA_REF_PREFIX)]
            if isinstance(ref, str) and ref.startswith(_SCHEMA_REF_PREFIX)
            else []
        )
        return names + [n for value in node.values() for n in _referenced_names(value)]
    if isinstance(node, list):
        return [n for item in node for n in _referenced_names(item)]
    return []


def _reachable(spec: APISpec, roots: list[str]) -> set[str]:
    schemas = spec.components.schemas
    seen: set[str] = set()
    pending = list(roots)
    while pending:
        name = pending.pop()
        if name in seen or name not in schemas:
            continue
        seen.add(name)
        pending.extend(_referenced_names(schemas[name]))
    return seen


def _shape_output_schemas(
    spec: APISpec,
    namer: _SchemaNamer,
    output_roots: list[str],
    input_roots: list[str],
) -> None:
    """
    Nos schemas usados só em respostas, remove os campos `load_only` e marca os
    demais como `required`, exceto os com `metadata={"output_optional": True}`. Sem
    isso, clientes gerados tratam todo campo de saída como opcional.
    """
    output_only = _reachable(spec, output_roots) - _reachable(spec, input_roots)
    for name in output_only:
        schema = namer.instances.get(name)
        if schema is None:
            continue
        component = spec.components.schemas[name]
        properties = component.get("properties", {})
        required = []
        for field_name, field in schema.fields.items():
            prop = field.data_key or field_name
            if field.load_only:
                properties.pop(prop, None)
            elif prop in properties and not field.metadata.get("output_optional"):
                required.append(prop)
        if required:
            component["required"] = required


def _register_partial_variants(spec: APISpec, roots: dict[str, frozenset[str]]) -> None:
    """
    Registra `Partial<Nome>` para os bodies de PATCH, espelhando o runtime: nenhum
    campo é obrigatório (inclusive nos aninhados) e os não atualizáveis do primeiro
    nível são descartados.
    """
    schemas = spec.components.schemas
    variants: dict[str, dict[str, Any]] = {}
    pending = list(roots)
    while pending:
        name = pending.pop()
        if name in variants:
            continue
        component = copy.deepcopy(schemas[name])
        component.pop("required", None)
        for prop in roots.get(name, frozenset()):
            component.get("properties", {}).pop(prop, None)
        pending.extend(_point_refs_to_partial(component))
        variants[name] = component

    for name, component in variants.items():
        spec.components.schema(_partial_name(name), component=component)


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
        body_schema = _schema_ref(op.request_body.schema)
        if op.request_body.partial:
            body_schema = {
                "$ref": _SCHEMA_REF_PREFIX
                + _partial_name(op.request_body.schema.__name__)
            }
        out["requestBody"] = {
            "required": op.request_body.required,
            "content": {op.request_body.content_type: {"schema": body_schema}},
        }
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

    _register_partial_variants(
        spec,
        {
            op.request_body.schema.__name__: _non_updatable_properties(
                op.request_body.schema
            )
            for op in all_operations
            if op.request_body is not None and op.request_body.partial
        },
    )

    _shape_output_schemas(
        spec,
        namer,
        output_roots=[
            *(
                schema.__name__
                for op in all_operations
                for response in op.responses
                if isinstance(schema := response.schema, type)
                and issubclass(schema, Schema)
            ),
            *(name for op in all_operations for name in op.extra_components),
        ],
        input_roots=[
            op.request_body.schema.__name__
            for op in all_operations
            if op.request_body is not None
        ],
    )

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
