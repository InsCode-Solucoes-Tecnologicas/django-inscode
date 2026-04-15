from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from marshmallow import Schema


def get_updatable_fields(schema: "Schema") -> set[str]:
    return {k for k, v in schema.fields.items() if v.metadata.get("updatable", True)}
