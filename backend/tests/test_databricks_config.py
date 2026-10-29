import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import DatabricksSettings
from app.db.databricks import DatabricksNotConfiguredError, databricks_connection, missing_settings

FAKE_TOKEN = "fake-token-for-tests"


def test_defaults_target_project_schema() -> None:
    settings = DatabricksSettings()

    assert settings.catalog == "workspace"
    assert settings.schema_name == "smartstock_retail"
    assert settings.is_configured is False


def test_reads_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABRICKS_SERVER_HOSTNAME", "example.cloud.databricks.com")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/abc")
    monkeypatch.setenv("DATABRICKS_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("DATABRICKS_SCHEMA", "other_schema")

    settings = DatabricksSettings()

    assert settings.is_configured is True
    assert settings.schema_name == "other_schema"
    assert settings.token is not None and settings.token.get_secret_value() == FAKE_TOKEN


def test_token_never_appears_in_repr_or_dump(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABRICKS_TOKEN", FAKE_TOKEN)

    settings = DatabricksSettings()

    assert FAKE_TOKEN not in repr(settings)
    assert FAKE_TOKEN not in str(settings)
    assert FAKE_TOKEN not in settings.model_dump_json()


def test_connection_refuses_when_not_configured() -> None:
    with pytest.raises(DatabricksNotConfiguredError) as exc_info:
        with databricks_connection(DatabricksSettings()):
            pass

    message = str(exc_info.value)
    assert "DATABRICKS_SERVER_HOSTNAME" in message
    assert "DATABRICKS_HTTP_PATH" in message
    assert "DATABRICKS_TOKEN" in message


def test_missing_settings_lists_only_absent_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABRICKS_SERVER_HOSTNAME", "example.cloud.databricks.com")
    monkeypatch.setenv("DATABRICKS_TOKEN", FAKE_TOKEN)

    assert missing_settings(DatabricksSettings()) == ["DATABRICKS_HTTP_PATH"]


def test_app_import_does_not_load_databricks_connector() -> None:
    # The connector is imported lazily, only when a connection is actually opened.
    # Checked in a fresh interpreter because other tests may already have imported app.main.
    result = subprocess.run(
        [sys.executable, "-c", "import sys, app.main; print('databricks.sql' in sys.modules)"],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert result.stdout.strip() == "False"
