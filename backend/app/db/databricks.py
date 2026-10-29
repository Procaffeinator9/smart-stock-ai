"""Databricks SQL Warehouse connection factory, plus error sanitising helpers.

Configuration comes exclusively from environment variables (see ``DatabricksSettings``).
Nothing here connects at import or application startup; a connection is opened only when
``databricks_connection()`` is explicitly entered. This module never executes SQL itself.

Every connection uses bounded timeouts and retries (``connection_options``) instead of the
connector's 900-second defaults, disables the connector's telemetry, and sets the session time
zone to UTC and a server-side statement timeout.
"""

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Literal

from app.core.config import DatabricksSettings, get_databricks_settings

if TYPE_CHECKING:
    from databricks.sql.client import Connection

logger = logging.getLogger(__name__)

# Backoff between retries of one request: connector-accepted ranges are 0.1-60 s (min) and 5-3600 s (max).
RETRY_DELAY_MIN_SECONDS = 1.0
RETRY_DELAY_MAX_SECONDS = 10.0


class DatabricksNotConfiguredError(RuntimeError):
    """Raised when a connection is requested but required DATABRICKS_* variables are missing."""


class InvalidIdentifierError(ValueError):
    """DATABRICKS_CATALOG / DATABRICKS_SCHEMA (or a table name) is not a simple identifier."""


def missing_settings(settings: DatabricksSettings) -> list[str]:
    missing = []
    if not settings.server_hostname:
        missing.append("DATABRICKS_SERVER_HOSTNAME")
    if not settings.http_path:
        missing.append("DATABRICKS_HTTP_PATH")
    if not settings.token or not settings.token.get_secret_value():
        missing.append("DATABRICKS_TOKEN")
    return missing


def connection_options(settings: DatabricksSettings) -> dict[str, Any]:
    """Keyword arguments for ``databricks.sql.connect`` besides the credentials."""
    return {
        "catalog": settings.catalog,
        "schema": settings.schema_name,
        "_socket_timeout": settings.socket_timeout_seconds,
        "_retry_stop_after_attempts_count": settings.retry_max_attempts,
        "_retry_stop_after_attempts_duration": settings.retry_max_duration_seconds,
        "_retry_delay_min": RETRY_DELAY_MIN_SECONDS,
        "_retry_delay_max": RETRY_DELAY_MAX_SECONDS,
        # Telemetry would send usage and error logs (including error text) to the workspace.
        "enable_telemetry": False,
        # With pyarrow installed, results arrive as Arrow batches. Convert them with Arrow's
        # .as_py() (plain int/bool/str/date/datetime/Decimal) rather than the connector's pandas
        # path. Defensive: with pandas 3.0.6 / numpy 2.5.4 both paths yield the same Python types
        # (tests check both), but the pandas path's types depend on pandas/numpy versions.
        # Without pyarrow, the connector falls back to row-based results and this has no effect.
        "_disable_pandas": True,
        "use_cloud_fetch": settings.use_cloud_fetch,
        "session_configuration": {
            "STATEMENT_TIMEOUT": str(settings.statement_timeout_seconds),
            "TIMEZONE": "UTC",
        },
    }


@contextmanager
def databricks_connection(settings: DatabricksSettings | None = None) -> Iterator["Connection"]:
    """Open a Databricks SQL connection for the duration of the ``with`` block."""
    settings = settings or get_databricks_settings()
    missing = missing_settings(settings)
    if missing:
        raise DatabricksNotConfiguredError(f"Databricks is not configured; missing: {', '.join(missing)}")

    # Imported lazily so the API and tests start without loading the connector.
    from databricks import sql

    # Never log the hostname, HTTP path, or token.
    logger.info("Opening Databricks SQL connection (catalog=%s, schema=%s)", settings.catalog, settings.schema_name)
    connection = sql.connect(
        server_hostname=settings.server_hostname,
        http_path=settings.http_path,
        access_token=settings.token.get_secret_value(),
        **connection_options(settings),
    )
    try:
        yield connection
    finally:
        connection.close()


# --- Identifiers ---------------------------------------------------------------------------------

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def quote_identifier(name: str) -> str:
    if not _IDENTIFIER.fullmatch(name):
        raise InvalidIdentifierError(f"'{name}' is not a simple identifier (letters, digits, underscore)")
    return f"`{name}`"


def qualified_schema(settings: DatabricksSettings) -> str:
    return f"{quote_identifier(settings.catalog)}.{quote_identifier(settings.schema_name)}"


def qualified_table(settings: DatabricksSettings, table: str) -> str:
    """`catalog`.`schema`.`table` from the configured catalog and schema."""
    return f"{qualified_schema(settings)}.{quote_identifier(table)}"


# --- Error sanitising ----------------------------------------------------------------------------

ErrorCategory = Literal["not_configured", "timeout", "auth", "not_found", "network", "query"]

ERROR_MESSAGES: dict[str, str] = {
    "not_configured": "Databricks is selected as the data source but is not configured.",
    "timeout": "Databricks did not respond within the configured timeout.",
    "auth": "Databricks rejected the credentials or permissions.",
    "not_found": "A Databricks catalog, schema, or table was not found.",
    "network": "Databricks could not be reached.",
    "query": "A Databricks query failed.",
}

_URL = re.compile(r"\b(?:https?|wss?)://\S+", re.IGNORECASE)
_PAT = re.compile(r"\bdapi[0-9a-f]{16,}(?:-\d+)?\b", re.IGNORECASE)
_KEY_VALUE = re.compile(r"(?i)\b(authorization|bearer|access_token|token|password|secret)\b(\s*[:=]\s*|\s+)\S+")
_MAX_LOG_TEXT = 300


def _secret_values(settings: DatabricksSettings | None) -> list[str]:
    if settings is None:
        return []
    values = [settings.server_hostname or "", settings.http_path or ""]
    if settings.token:
        values.append(settings.token.get_secret_value())
    return sorted({v for v in values if len(v) >= 4}, key=len, reverse=True)


def redact(text: str, settings: DatabricksSettings | None = None) -> str:
    """Remove configured secrets, URLs, token-like strings, and credential key/values from text."""
    for secret in _secret_values(settings):
        text = text.replace(secret, "[redacted]")
    text = _URL.sub("[url]", text)
    text = _PAT.sub("[token]", text)
    text = _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}[redacted]", text)
    return text


def sanitize_error(exc: BaseException, settings: DatabricksSettings | None = None) -> str:
    """One-line, redacted, length-limited description safe for logs and terminals (not API clients)."""
    text = " ".join(redact(f"{type(exc).__name__}: {exc}", settings).split())
    return text if len(text) <= _MAX_LOG_TEXT else text[: _MAX_LOG_TEXT - 1] + "…"


def classify_error(exc: BaseException) -> ErrorCategory:
    """Coarse category for an exception raised while connecting or querying."""
    names = {cls.__name__ for cls in type(exc).__mro__}
    message = str(exc).lower()
    if isinstance(exc, DatabricksNotConfiguredError):
        return "not_configured"
    if isinstance(exc, TimeoutError) or "MaxRetryDurationError" in names or "timed out" in message or "timeout" in message:
        return "timeout"
    if any(s in message for s in ("401", "403", "unauthorized", "forbidden", "invalid access token", "permission_denied", "permission denied")):
        return "auth"
    if any(s in message for s in ("table_or_view_not_found", "schema_not_found", "catalog_not_found", "not found")):
        return "not_found"
    if isinstance(exc, (ConnectionError, OSError)) or "RequestError" in names:
        return "network"
    return "query"
