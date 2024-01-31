import csv
import json
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from functools import partial
from http import HTTPStatus
from pathlib import Path
from typing import Any, TypedDict, cast, get_type_hints
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


def export_dicts_to_csv(
    dicts: list[dict[str, Any]],
    csv_file_path: Path,
    fieldnames: list[str],
) -> None:
    """Exports a list of dictionaries to a CSV file.

    Args:
        dicts (list[dict[str, Any]]): A list of dictionaries to be written to the CSV.
        csv_file_path (str): The file path where the CSV should be saved.
        fieldnames (list[str]): The list of keys that will be the header of the CSV.
    """
    with open(file=csv_file_path, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
            escapechar="\\",
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        writer.writerows(dicts)


def convert_document_to_markdown(
    document: Document,
) -> str:
    return "".join([
        _generate_heading(
            document["request_method"],
            document["request_path"],
            document["request_query_string"],
        ),
        (
            "\n\n" + _generate_query_parameter(document["request_query_string"])
            if document["request_query_string"]
            else ""
        ),
        (
            "\n\n" + _generate_request_header(document["request_content_type"])
            if document["request_content_type"]
            and document["request_content_type"] != "application/json"
            else ""
        ),
        (
            "\n\n" + _generate_request_body(document["request_body"])
            if document["request_method"] != HTTPMethod.GET
            else ""
        ),
        "\n\n"
        + _generate_response_body(
            document["response_status_code"],
            document["response_body"],
        ),
    ])


def _generate_heading(
    request_method: HTTPMethod,
    request_path: str,
    query_string: dict[str, str],
    level: int = 3,
) -> str:
    """
    Example:
        ### GET `/api/users/?page={page}&size={size}`

    Example:
        ### POST `/api/users/?type=personal`
    """
    if request_method == HTTPMethod.GET:
        for key, value in query_string.items():
            request_path = request_path.replace(f"{key}={value}", f"{key}={{{key}}}")

    return f"{'#' * level} {request_method} `{request_path}`"


def _generate_query_parameter(
    query_string: dict[str, str],
) -> str:
    """
    Example:
        Query Parameter

        - `page`: `1`
        - `size`: `10`
    """
    return "Query Parameter\n\n" + "\n".join(
        f"- `{key}`: `{value}`" for key, value in query_string.items()
    )


def _generate_request_header(
    request_content_type: str,
):
    """

    Example:
        Request Header

        - Content-Type: `application/json`
    """
    return f"Request Header\n\n- Content-Type: `{request_content_type}`"


def _generate_request_body(
    request_body: str | None,
) -> str:
    """
    Example (request_body is not None):
        Request Body

        ```json
        {
            "name": "John Doe",
            "phoneNumber": "01012345678",
        }
        ```

    Example (request_body is None):
        Request Body

        ```json

        ```
    """
    return f"Request Body\n\n```json\n{request_body or ''}\n```"


def _generate_response_body(
    response_status_code: HTTPStatus,
    response_body: str | None,
) -> str:
    """
    Example (response_body != ""):
        Response Body (200)

        ```json
        {
            "name": "John Doe",
            "phoneNumber": "01012345678",
        }
        ```

    Example (response_body == ""):
        Response Body (204)

        ```json

        ```
    """
    return (
        f"Response Body ({response_status_code})\n\n```json\n{response_body or ''}\n```"
    )


def convert_documents_to_markdown(
    documents: list[Document],
) -> str:
    return "\n\n".join(
        [convert_document_to_markdown(document) for document in documents]
    )


def export_markdown_to_file(
    markdown: str,
    file_path: Path,
) -> None:
    with open(file=file_path, mode="w", encoding="utf-8") as file:
        file.write(markdown)


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
    export_dicts_to_csv(
        cast(list[dict[str, Any]], documents),
        har_file_path.with_suffix(".csv"),
        fieldnames=list(get_type_hints(Document).keys()),
    )
    export_markdown_to_file(
        convert_documents_to_markdown(documents),
        har_file_path.with_suffix(".md"),
    )


if __name__ == "__main__":
    main()
