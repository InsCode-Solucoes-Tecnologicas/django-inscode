from typing import TYPE_CHECKING, Any, Literal, Required, TypedDict, TypeVar
from uuid import UUID

if TYPE_CHECKING:
    from marshmallow import Schema
    from marshmallow.fields import Field

type Data = dict[str, Any]


class Context(TypedDict):
    user: Any
    session: Any
    url_params: dict
    query_params: dict


HttpMethod = Literal["get", "post", "put", "patch", "delete"]

ParameterLocation = Literal["path", "query", "header", "cookie"]


class ParameterOverride(TypedDict, total=False):
    name: Required[str]
    location: Required[ParameterLocation]
    schema: Required[dict[str, Any]]
    required: bool
    description: str


class ResponseOverride(TypedDict, total=False):
    """Sem `schema`, a introspecção usa o schema de saída da view."""

    status_code: Required[int]
    description: Required[str]
    schema: "type[Schema] | dict[str, Any] | None"


class MethodOpenAPIMetadata(TypedDict, total=False):
    parameters: list[ParameterOverride]
    responses: list[ResponseOverride]
    field: "Field"


class MethodMetadata(TypedDict, total=False):
    openapi: MethodOpenAPIMetadata


Id = TypeVar("Id", UUID, int)
