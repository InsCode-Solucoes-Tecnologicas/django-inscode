from collections.abc import Callable
from typing import Any

from django_inscode.types import MethodMetadata


def metadata[F: Callable[..., Any]](data: MethodMetadata) -> Callable[[F], F]:
    """Anexa metadados a um método de view; métodos sobrescritos sem eles herdam os da base."""

    def decorator(method: F) -> F:
        method.metadata = data  # type: ignore[attr-defined]
        return method

    return decorator


__all__ = ["metadata"]
