from __future__ import annotations

from typing import Any

from marshmallow import Schema, fields


class PaginationSchema(Schema):
    """Metadados de paginação retornados em respostas de listagem."""

    current_page = fields.Integer(required=True)
    total_items = fields.Integer(required=True)
    total_pages = fields.Integer(required=True)
    has_next = fields.Boolean(required=True)
    has_previous = fields.Boolean(required=True)


class ErrorResponseSchema(Schema):
    """Formato padrão de erro emitido por `APIException.to_dict()`."""

    code = fields.Integer(required=True)
    message = fields.String(required=True)
    errors = fields.Raw(required=False)


def paginated_response_schema(item_schema_name: str) -> dict[str, Any]:
    """Constrói o JSON Schema (OpenAPI) de uma resposta paginada de `item_schema_name`."""
    return {
        "type": "object",
        "properties": {
            "pagination": {"$ref": "#/components/schemas/Pagination"},
            "results": {
                "type": "array",
                "items": {"$ref": f"#/components/schemas/{item_schema_name}"},
            },
        },
        "required": ["pagination", "results"],
    }


__all__ = [
    "PaginationSchema",
    "ErrorResponseSchema",
    "paginated_response_schema",
]
