from typing import Any, TypedDict, TypeVar
from uuid import UUID

type Data = dict[str, Any]


class Context(TypedDict):
    user: Any
    session: Any
    url_params: dict
    query_params: dict


Id = TypeVar("Id", UUID, int)
