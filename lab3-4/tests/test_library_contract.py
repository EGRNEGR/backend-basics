import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate

SPEC_PATH = Path(__file__).resolve().parents[1] / "library-api" / "openapi.yaml"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
REQUIRED_ERROR_CODES = {
    "INVALID_REQUEST",
    "NOT_FOUND",
    "VALIDATION_ERROR",
    "CONFLICT",
    "BUSINESS_RULE_VIOLATION",
    "IDEMPOTENCY_MISMATCH",
}
SERVER_FIELDS = {
    "id",
    "available_copies",
    "registered_at",
    "loaned_at",
    "returned_at",
    "status",
}
KEBAB_SEGMENT = re.compile(r"^([a-z0-9]+(-[a-z0-9]+)*|\{[a-z][a-z0-9_]*\})$")
SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


def iter_operations(spec: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method in HTTP_METHODS:
                yield path, method, operation


def node_ref_parts(ref: str) -> list[str]:
    return ref.removeprefix("#/").split("/")


def deref(spec: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        target: Any = spec
        for part in node_ref_parts(node["$ref"]):
            target = target[part]
        node = target
    return node


def iter_properties(schema: dict[str, Any]) -> Iterator[str]:
    yield from schema.get("properties", {})
    for nested in schema.get("properties", {}).values():
        if isinstance(nested, dict):
            yield from iter_properties(nested)


def iter_examples(spec: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any], Any]]:
    def from_media(
        where: str, media: dict[str, Any]
    ) -> Iterator[tuple[str, dict[str, Any], Any]]:
        if "example" in media:
            yield where, media["schema"], media["example"]
        for name, example in media.get("examples", {}).items():
            yield f"{where} [{name}]", media["schema"], example["value"]

    for path, method, operation in iter_operations(spec):
        body = operation.get("requestBody", {}).get("content", {})
        for media in body.values():
            yield from from_media(f"{method.upper()} {path} request", media)
        for status, response in operation["responses"].items():
            for media in deref(spec, response).get("content", {}).values():
                yield from from_media(f"{method.upper()} {path} {status}", media)


def test_spec_is_valid_openapi_3_1(spec: dict[str, Any]) -> None:
    assert spec["openapi"].startswith("3.1")
    validate(spec)


def test_servers_are_versioned(spec: dict[str, Any]) -> None:
    public = [
        s["url"] for s in spec["servers"] if not s["url"].startswith("http://127.0.0.1")
    ]
    assert public
    assert all(url.endswith("/v1") for url in public)


def test_paths_are_kebab_case_nouns(spec: dict[str, Any]) -> None:
    for path in spec["paths"]:
        for segment in path.strip("/").split("/"):
            assert KEBAB_SEGMENT.match(segment), f"{path}: segment {segment!r}"


def test_json_properties_and_query_params_are_snake_case(spec: dict[str, Any]) -> None:
    for name, schema in spec["components"]["schemas"].items():
        for prop in iter_properties(schema):
            assert SNAKE_CASE.match(prop), f"{name}.{prop}"
    params = list(spec["components"]["parameters"].values())
    for _, _, operation in iter_operations(spec):
        params.extend(deref(spec, p) for p in operation.get("parameters", []))
    for param in params:
        if param["in"] in {"query", "path"}:
            assert SNAKE_CASE.match(param["name"]), param["name"]


def test_crud_and_loan_operations_exist(spec: dict[str, Any]) -> None:
    operations = {(method, path) for path, method, _ in iter_operations(spec)}
    expected = {
        ("get", "/books"), ("post", "/books"),
        ("get", "/books/{book_id}"), ("patch", "/books/{book_id}"), ("delete", "/books/{book_id}"),
        ("get", "/readers"), ("post", "/readers"),
        ("get", "/readers/{reader_id}"), ("patch", "/readers/{reader_id}"),
        ("delete", "/readers/{reader_id}"),
        ("get", "/loans"), ("post", "/loans"), ("get", "/loans/{loan_id}"),
        ("post", "/loans/{loan_id}/return"),
    }  # fmt: skip
    assert expected <= operations
    assert ("delete", "/loans/{loan_id}") not in operations


def test_status_codes_follow_conventions(spec: dict[str, Any]) -> None:
    for path, method, operation in iter_operations(spec):
        codes = set(operation["responses"])
        if method == "post" and not path.endswith("/return"):
            assert "201" in codes, f"POST {path}"
            assert "Location" in operation["responses"]["201"]["headers"]
        if method == "delete":
            assert "204" in codes and "content" not in operation["responses"]["204"]
        if "{" in path:
            assert "404" in codes, f"{method.upper()} {path}"


def test_every_error_uses_error_response(spec: dict[str, Any]) -> None:
    for path, method, operation in iter_operations(spec):
        for status, response in operation["responses"].items():
            if status.startswith("4"):
                schema = deref(spec, response)["content"]["application/json"]["schema"]
                assert schema == {"$ref": "#/components/schemas/ErrorResponse"}, (
                    f"{method.upper()} {path} {status}"
                )


def test_error_codes_cover_requirements(spec: dict[str, Any]) -> None:
    codes = set(spec["components"]["schemas"]["ErrorCode"]["enum"])
    assert REQUIRED_ERROR_CODES <= codes


def test_collections_have_filters_sort_and_pagination(spec: dict[str, Any]) -> None:
    limit = spec["components"]["parameters"]["Limit"]["schema"]
    assert limit["default"] == 20 and limit["maximum"] == 100
    for path in ("/books", "/readers", "/loans"):
        params = [deref(spec, p) for p in spec["paths"][path]["get"]["parameters"]]
        names = {p["name"] for p in params}
        assert {"limit", "offset", "sort"} <= names, path
        assert len(names - {"limit", "offset", "sort"}) >= 3, f"{path}: too few filters"
        sort = next(p for p in params if p["name"] == "sort")["schema"]
        assert "default" in sort and all(v.lstrip("-") for v in sort["enum"])


def test_overdue_loans_filter(spec: dict[str, Any]) -> None:
    params = spec["paths"]["/loans"]["get"]["parameters"]
    status = next(p for p in params if p.get("name") == "status")
    assert "overdue" in deref(spec, status["schema"])["enum"]


def test_request_schemas_reject_unknown_and_server_fields(spec: dict[str, Any]) -> None:
    schemas = spec["components"]["schemas"]
    requests = [name for name in schemas if name.endswith("Request")]
    assert len(requests) == 5
    for name in requests:
        assert schemas[name]["additionalProperties"] is False, name
        assert not SERVER_FIELDS & set(schemas[name]["properties"]), name
    assert schemas["Book"]["properties"]["available_copies"]["readOnly"] is True


def test_create_loan_requires_idempotency_key(spec: dict[str, Any]) -> None:
    operation = spec["paths"]["/loans"]["post"]
    header = deref(spec, operation["parameters"][0])
    assert header["name"] == "Idempotency-Key" and header["in"] == "header"
    assert header["required"] is True and header["schema"]["format"] == "uuid"
    description = operation["description"]
    for phrase in ("replay", "IDEMPOTENCY_MISMATCH", "конкурентный повтор", "24 часа"):
        assert phrase in description, phrase


def test_operations_are_documented(spec: dict[str, Any]) -> None:
    operation_ids = []
    for path, method, operation in iter_operations(spec):
        where = f"{method.upper()} {path}"
        assert operation.get("summary") and operation.get("description"), where
        assert len(operation["tags"]) == 1, where
        assert operation["tags"][0] in {"Books", "Readers", "Loans"}, where
        operation_ids.append(operation["operationId"])
    assert len(operation_ids) == len(set(operation_ids))


def test_examples_match_their_schemas(spec: dict[str, Any]) -> None:
    examples = list(iter_examples(spec))
    assert len(examples) >= 3
    assert any(
        status in where for where, _, _ in examples for status in (" 409", " 422")
    )
    for where, schema, value in examples:
        validator = Draft202012Validator(
            {**schema, "components": spec["components"]},
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )
        errors = [error.message for error in validator.iter_errors(value)]
        assert not errors, f"{where}: {errors}"


def test_bonus_security_and_deprecation(spec: dict[str, Any]) -> None:
    scheme = spec["components"]["securitySchemes"]["bearer_auth"]
    assert scheme == {
        **scheme,
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    assert spec["security"] == [{"bearer_auth": []}]
    assert (
        spec["components"]["schemas"]["Loan"]["properties"]["is_overdue"]["deprecated"]
        is True
    )
