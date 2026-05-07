from __future__ import annotations

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


_REGISTRY: dict[type[BaseAuthentication], tuple[str, SecurityScheme]] = {}


def register_security_scheme(
    auth_class: type[BaseAuthentication],
    *,
    name: str,
    scheme: SecurityScheme,
) -> None:
    """
    Associa uma classe `BaseAuthentication` a um Security Scheme OpenAPI.

    Args:
        auth_class: classe (ou base) a ser detectada nas views.
        name: identificador do scheme em `components.securitySchemes`.
        scheme: objeto Security Scheme (https://spec.openapis.org/oas/v3.0.3#security-scheme-object).
    """
    _REGISTRY[auth_class] = (name, scheme)


def registered_schemes() -> dict[str, SecurityScheme]:
    """Devolve o mapa nome → scheme para registro em `components.securitySchemes`."""
    return {name: scheme for name, scheme in _REGISTRY.values()}


def _resolve_auth_classes(view_class: type[View]) -> list[type[BaseAuthentication]]:
    """
    Resolve as classes de autenticação ativas em uma view.

    Replica a lógica de `GenericView.__init__`: usa `authentication_classes` se
    definida, senão recorre a `settings.DEFAULT_AUTHENTICATION_CLASSES`.
    """
    declared: list[type[BaseAuthentication]] = list(
        getattr(view_class, "authentication_classes", []) or []
    )
    if declared:
        return declared

    paths: list[str] = list(getattr(settings, "DEFAULT_AUTHENTICATION_CLASSES", []))
    return [import_string(path) for path in paths]


def security_for_view(view_class: type[View]) -> list[SecurityRequirement]:
    """
    Devolve a lista de Security Requirements para uma view.

    Lista vazia → endpoint público. Múltiplos schemes resolvem como `OR`
    (qualquer um satisfaz).
    """
    requirements: list[SecurityRequirement] = []
    seen: set[str] = set()

    for auth_class in _resolve_auth_classes(view_class):
        for registered_class, (name, _) in _REGISTRY.items():
            if not (
                auth_class is registered_class
                or issubclass(auth_class, registered_class)
            ):
                continue
            if name in seen:
                continue
            requirements.append({name: []})
            seen.add(name)
            break

    return requirements


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
    "security_for_view",
]
