from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from django.urls import URLPattern, URLResolver, get_resolver
from django.urls.converters import (
    IntConverter,
    SlugConverter,
    StringConverter,
    UUIDConverter,
)
from django.urls.resolvers import RegexPattern, RoutePattern
from django.views import View

from django_inscode.openapi.types import CollectedRoute, ParameterSpec

_ROUTE_PARAM_RE = re.compile(r"<(?:(?P<conv>\w+):)?(?P<name>\w+)>")


def _converter_to_schema(converter: Any) -> dict[str, Any]:
    """Mapeia um path converter Django para um JSON Schema OpenAPI."""
    match converter:
        case IntConverter():
            return {"type": "integer"}
        case UUIDConverter():
            return {"type": "string", "format": "uuid"}
        case StringConverter() | SlugConverter():
            return {"type": "string"}
        case _:
            return {"type": "string"}


def _route_pattern_to_template(
    pattern: RoutePattern,
) -> tuple[str, tuple[ParameterSpec, ...]]:
    """Converte `<conv:name>` em `{name}` e produz parâmetros de path tipados."""
    raw: str = pattern._route
    parameters: list[ParameterSpec] = []

    for match in _ROUTE_PARAM_RE.finditer(raw):
        name = match.group("name")
        converter = pattern.converters.get(name)
        schema = _converter_to_schema(converter) if converter else {"type": "string"}
        parameters.append(
            ParameterSpec(
                name=name,
                location="path",
                schema=schema,
                required=True,
            )
        )

    template = _ROUTE_PARAM_RE.sub(lambda m: "{" + m.group("name") + "}", raw)
    return template, tuple(parameters)


def _regex_pattern_to_template(
    pattern: RegexPattern,
) -> tuple[str, tuple[ParameterSpec, ...]]:
    """Best-effort: extrai grupos nomeados de uma re_path como params string."""
    regex = pattern.regex
    parameters = tuple(
        ParameterSpec(
            name=name,
            location="path",
            schema={"type": "string"},
            required=True,
        )
        for name in regex.groupindex
    )
    template = pattern._regex.lstrip("^").rstrip("$")
    template = re.sub(r"\(\?P<(\w+)>[^)]+\)", lambda m: "{" + m.group(1) + "}", template)
    return template, parameters


def _normalize_template(prefix: str, suffix: str) -> str:
    """Garante uma única `/` ao concatenar e prefixo `/`."""
    combined = (prefix + suffix).replace("//", "/")
    if not combined.startswith("/"):
        combined = "/" + combined
    return combined


def _walk(
    patterns: list[URLPattern | URLResolver],
    prefix: str,
    prefix_params: tuple[ParameterSpec, ...],
) -> Iterator[CollectedRoute]:
    for entry in patterns:
        match entry:
            case URLResolver():
                sub_template, sub_params = _extract_template(entry.pattern)
                yield from _walk(
                    entry.url_patterns,
                    _normalize_template(prefix, sub_template),
                    prefix_params + sub_params,
                )
            case URLPattern():
                view_class = getattr(entry.callback, "view_class", None)
                if not (
                    isinstance(view_class, type) and issubclass(view_class, View)
                ):
                    continue
                sub_template, sub_params = _extract_template(entry.pattern)
                yield CollectedRoute(
                    path=_normalize_template(prefix, sub_template),
                    path_parameters=prefix_params + sub_params,
                    view_class=view_class,
                    name=entry.name,
                )


def _extract_template(
    pattern: RoutePattern | RegexPattern | Any,
) -> tuple[str, tuple[ParameterSpec, ...]]:
    match pattern:
        case RoutePattern():
            return _route_pattern_to_template(pattern)
        case RegexPattern():
            return _regex_pattern_to_template(pattern)
        case _:
            return "", ()


def collect_routes(urlconf: str | None = None) -> list[CollectedRoute]:
    """Percorre a URLConf e devolve todas as rotas atreladas a class-based views."""
    resolver = get_resolver(urlconf)
    return list(_walk(resolver.url_patterns, prefix="", prefix_params=()))


__all__ = ["collect_routes"]
