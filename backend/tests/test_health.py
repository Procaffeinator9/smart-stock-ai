import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_health_ok_without_databricks_credentials(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "SmartStock AI API",
        "version": __version__,
        "environment": "local",
        "databricks_configured": False,
        "data_source": "csv",
    }


def test_health_reports_configured_without_leaking_values(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABRICKS_SERVER_HOSTNAME", "adb-0000000000000000.0.azuredatabricks.net")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/fake")
    monkeypatch.setenv("DATABRICKS_TOKEN", "fake-token-for-tests")

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["databricks_configured"] is True
    for secret_ish in ("fake-token-for-tests", "azuredatabricks.net", "/sql/1.0/warehouses"):
        assert secret_ish not in response.text


def test_unknown_route_returns_404(client: TestClient) -> None:
    assert client.get("/api/v1/does-not-exist").status_code == 404
