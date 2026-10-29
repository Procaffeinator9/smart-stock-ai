import pytest

from app.core.config import get_databricks_settings, get_settings
from app.data.repository import clear_repository_cache


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory):
    """Keep tests independent of the developer's shell env and backend/.env file."""
    for name in (
        "DATABRICKS_SERVER_HOSTNAME",
        "DATABRICKS_HTTP_PATH",
        "DATABRICKS_TOKEN",
        "DATABRICKS_CATALOG",
        "DATABRICKS_SCHEMA",
        "SMARTSTOCK_ENVIRONMENT",
        "SMARTSTOCK_DATA_SOURCE",
        "SMARTSTOCK_DATA_DIR",
        "SMARTSTOCK_DATA_REFRESH_SECONDS",
        "SMARTSTOCK_DATA_WAIT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    # Point the settings at a non-existent .env so a real backend/.env is never read.
    empty_env = tmp_path_factory.mktemp("env") / ".env"
    from app.core import config

    monkeypatch.setitem(config.DatabricksSettings.model_config, "env_file", empty_env)
    monkeypatch.setitem(config.Settings.model_config, "env_file", empty_env)
    get_settings.cache_clear()
    get_databricks_settings.cache_clear()
    clear_repository_cache()
    yield
    get_settings.cache_clear()
    get_databricks_settings.cache_clear()
    clear_repository_cache()
