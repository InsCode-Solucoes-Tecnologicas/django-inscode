from typing import Any, TypedDict

type Data = dict[str, Any]


class Context(TypedDict):
    user: Any
    session: Any
    url_params: dict
    query_params: dict
