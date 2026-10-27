from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from django.core.management import call_command
from django.test import Client

SCHEMA_URL = "/api/v1/schema/"

EXPECTED_PATHS = {
    "/api/v1/auth/csrf/",
    "/api/v1/auth/login/",
    "/api/v1/auth/logout/",
    "/api/v1/auth/me/",
    "/api/v1/workspaces/{workspace_id}/tickets/",
    "/api/v1/workspaces/{workspace_id}/tickets/{ticket_id}/",
    "/api/v1/workspaces/{workspace_id}/tickets/{ticket_id}/assign/",
    "/api/v1/workspaces/{workspace_id}/tickets/{ticket_id}/transition/",
    "/api/v1/workspaces/{workspace_id}/tickets/{ticket_id}/messages/",
}


def test_schema_is_publicly_retrievable(client: Client) -> None:
    response = client.get(SCHEMA_URL)

    assert response.status_code == 200


def test_schema_documents_auth_endpoints_with_cookie_auth(client: Client) -> None:
    schema = yaml.safe_load(client.get(SCHEMA_URL).content)

    assert EXPECTED_PATHS <= set(schema["paths"])
    security_schemes = schema.get("components", {}).get("securitySchemes", {})
    assert "cookieAuth" in security_schemes


def test_schema_passes_its_own_validator(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "schema.yaml"

    call_command("spectacular", "--validate", "--file", str(destination))

    output = capsys.readouterr()
    # The command prints a warning summary only when it finds problems.
    assert re.search(r"Errors:\s+[1-9]", output.err) is None, output.err

    schema = yaml.safe_load(destination.read_text(encoding="utf-8"))
    assert schema["openapi"].startswith("3.")


def test_schema_does_not_expose_the_schema_view_itself(client: Client) -> None:
    schema = yaml.safe_load(client.get(SCHEMA_URL).content)

    assert SCHEMA_URL not in schema["paths"]
