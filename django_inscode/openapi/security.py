from __future__ import annotations

import warnings
from collections.abc import Iterable
from typing import Any

from django.conf import settings
from django.utils.module_loading import import_string
from django.views import View

from django_inscode.authentication import (
    BaseAuthentication,
    KeycloakBearerAuthentication,
)

SecurityScheme = dict[str, Any]
SecurityRequirement = dict[str, list[str]]


_REGISTRY: dict[type[BaseAuthentication], tuple[tuple[str, SecurityScheme], ...]] = {}
_WARNED: set[type[BaseAuthentication]] = set()


def register_security_scheme(
    auth_class: type[BaseAuthentication],
    *,
    name: str,
    scheme: SecurityScheme,
) -> None:
    """
    Associa uma classe `BaseAuthentication` a um Security Scheme OpenAPI.

    Registrar mais de um scheme para a mesma classe significa que todos são
    exigidos juntos (`AND`), na ordem de registro.

    Args:
        auth_class: classe (ou base) a ser detectada nas views.
        name: identificador do scheme em `components.securitySchemes`.
        scheme: objeto Security Scheme (https://spec.openapis.org/oas/v3.0.3#security-scheme-object).
    """
    current = _REGISTRY.get(auth_class, ())
    _REGISTRY[auth_class] = (*(s for s in current if s[0] != name), (name, scheme))


def registered_schemes() -> dict[str, SecurityScheme]:
    """Devolve o mapa nome → scheme de todos os schemes registrados."""
    return {name: scheme for schemes in _REGISTRY.values() for name, scheme in schemes}


def _schemes_for(
    auth_class: type[BaseAuthentication],
) -> tuple[tuple[str, SecurityScheme], ...] | None:
    for registered_class in auth_class.__mro__:
        if registered_class in _REGISTRY:
            return _REGISTRY[registered_class]
    return None


def _resolve_auth_classes(view_class: type[View]) -> list[type[BaseAuthentication]]:
    """
    Resolve as classes de autenticação ativas em uma view.

    Replica a lógica de `GenericView.__init__`: usa `authentication_classes` se
    declarada (`[]` inclusive), senão recorre a `settings.DEFAULT_AUTHENTICATION_CLASSES`.
    """
    declared: list[type[BaseAuthentication]] | None = getattr(
        view_class, "authentication_classes", None
    )
    if declared is not None:
        return list(declared)
    return default_authentication_classes()


def default_authentication_classes() -> list[type[BaseAuthentication]]:
    paths: list[str] = list(getattr(settings, "DEFAULT_AUTHENTICATION_CLASSES", []))
    return [import_string(path) for path in paths]


def security_for_auth_classes(
    auth_classes: Iterable[type[BaseAuthentication]],
) -> list[SecurityRequirement]:
    """
    Converte classes de autenticação em Security Requirements.

    Cada classe vira uma alternativa (`OR`), na ordem declarada. Classes sem
    scheme registrado são ignoradas com um aviso.
    """
    requirements: list[SecurityRequirement] = []
    seen: set[tuple[str, ...]] = set()

    for auth_class in auth_classes:
        schemes = _schemes_for(auth_class)
        if schemes is None:
            if auth_class not in _WARNED:
                _WARNED.add(auth_class)
                warnings.warn(
                    f"{auth_class.__module__}.{auth_class.__qualname__} não tem "
                    "security scheme registrado e foi omitida da spec OpenAPI. "
                    "Use django_inscode.openapi.register_security_scheme().",
                    stacklevel=2,
                )
            continue
        key = tuple(name for name, _ in schemes)
        if key in seen:
            continue
        seen.add(key)
        requirements.append({name: [] for name in key})

    return requirements


def security_for_view(view_class: type[View]) -> list[SecurityRequirement]:
    """
    Devolve a lista de Security Requirements para uma view.

    Lista vazia → endpoint público.
    """
    return security_for_auth_classes(_resolve_auth_classes(view_class))


def default_security() -> list[SecurityRequirement]:
    """Security Requirements de `settings.DEFAULT_AUTHENTICATION_CLASSES`."""
    return security_for_auth_classes(default_authentication_classes())


register_security_scheme(
    KeycloakBearerAuthentication,
    name="bearerAuth",
    scheme={
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Token Bearer OIDC (Keycloak).",
    },
)


__all__ = [
    "SecurityScheme",
    "SecurityRequirement",
    "register_security_scheme",
    "registered_schemes",
    "security_for_auth_classes",
    "security_for_view",
    "default_security",
]
