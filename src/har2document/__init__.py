import sys
from datetime import datetime
from http import HTTPStatus
from typing import TypedDict

if sys.version_info >= (3, 11):
    from http import HTTPMethod
else:
    from _http import HTTPMethod


class Document(TypedDict):
    request_datetime: datetime
    request_method: HTTPMethod
    request_url: str
    request_host: str
    request_path: str
    request_query_string: dict[str, str]
    request_content_type: str | None
    request_body: str | None
    response_datetime: datetime
    response_status_code: HTTPStatus
    response_content_type: str | None
    response_body: str | None
    time_elapsed: int
