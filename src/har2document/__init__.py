import json
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from functools import partial
from http import HTTPStatus
from pathlib import Path
from typing import TypedDict
from urllib.parse import unquote_plus

if sys.version_info >= (3, 11):
    from http import HTTPMethod
else:
    from _http import HTTPMethod

from haralyzer import HarEntry, HarParser
from haralyzer.http import Request, Response


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
    response_body: str
    time_elapsed: int


def parse_start_time(datetime_str: str) -> datetime:
    """input: "2024-01-31T14:42:19.605+09:00" """
    return datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S.%f%z").astimezone()


def parse_response_date(datetime_str: str) -> datetime:
    """input: "Mon, 01 Nov 2021 07:00:00 GMT" """
    return (
        datetime.strptime(datetime_str, "%a, %d %b %Y %H:%M:%S GMT")
        .replace(tzinfo=timezone.utc)
        .astimezone()
    )


def parse_request_query_string(query_string: list[dict[str, str]]) -> dict[str, str]:
    return {query["name"]: query["value"] for query in query_string}


def parse_body_text(text: str, content_type: str) -> str:
    # TODO: Add more content type
    def _format_json_pretty(json_str: str) -> str:
        return json.dumps(json.loads(json_str), indent=4, ensure_ascii=False)

    match content_type:
        case "application/json":
            return _format_json_pretty(text)
        case _:
            return text


def replace_string_by_mapping(body_text: str, mapping: dict[str, str]) -> str:
    for key, value in mapping.items():
        body_text = body_text.replace(key, value)
    return body_text


def convert_har_entry_to_document(
    entry: HarEntry,
    replace_string: Callable[[str], str],
) -> Document:
    request: Request = entry.request
    response: Response = entry.response

    return {
        "request_method": request.method,
        "request_datetime": parse_start_time(
            entry.raw_entry["startedDateTime"]
        ),  # Do not use parser provided by haralyze
        "request_url": unquote_plus(request.url),
        "request_host": unquote_plus(request.host),
        "request_path": unquote_plus(request.url.split(request.host)[-1]),
        "request_query_string": parse_request_query_string(request.queryString),
        "request_content_type": request.mimeType,
        "request_body": request.text
        and replace_string(parse_body_text(request.text, request.mimeType)),
        "response_datetime": parse_response_date(response.date),
        "response_status_code": response.status,
        "response_content_type": response.mimeType,
        "response_body": response.text
        and replace_string(parse_body_text(response.text, response.mimeType)),
        "time_elapsed": entry.time,
    }


def convert_har_file_to_documents(
    har_file_path: Path,
    masking_mapping: dict[str, str],
) -> list[Document]:
    har_parser = HarParser.from_file(har_file_path)
    replace_string: Callable[[str], str] = partial(
        replace_string_by_mapping,
        mapping=masking_mapping,
    )
    return [
        convert_har_entry_to_document(entry, replace_string)
        for page in har_parser.pages
        for entry in page.entries
    ]


def main() -> None:
    # TODO: Get input from a client
    har_file_path: Path = Path("sample.har")
    masking_mapping: dict[str, str] = {
        "realpassword!@": "1q2w3e4r!@",
        "01012345678": "01000000000",
    }

    documents: list[Document] = convert_har_file_to_documents(
        har_file_path,
        masking_mapping,
    )

    print(documents)


if __name__ == "__main__":
    main()
