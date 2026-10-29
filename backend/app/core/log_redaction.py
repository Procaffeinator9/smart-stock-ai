"""Logging safeguards: redact Databricks secrets from every log record."""

import logging

from app.core.config import DatabricksSettings


class SecretRedactionFilter(logging.Filter):
    """Rewrites each record's message with app.db.databricks.redact (configured secrets, URLs, tokens)."""

    def __init__(self, settings: DatabricksSettings):
        super().__init__()
        self.settings = settings

    def filter(self, record: logging.LogRecord) -> bool:
        from app.db.databricks import redact

        message = record.getMessage()
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        record.msg, record.args = redact(message, self.settings), None
        if record.exc_text:
            record.exc_text = redact(record.exc_text, self.settings)
        return True


def install_secret_redaction(settings: DatabricksSettings) -> None:
    """Attach the redaction filter to every root handler (idempotent).

    Loggers such as ``databricks.sql`` and ``urllib3`` propagate to the root handlers, so their
    records are redacted too. The connector's chatty loggers are capped at WARNING.
    """
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.WARNING)
    for handler in root.handlers:
        if not any(isinstance(f, SecretRedactionFilter) for f in handler.filters):
            handler.addFilter(SecretRedactionFilter(settings))
    for name in ("databricks.sql", "databricks", "urllib3", "thrift"):
        logging.getLogger(name).setLevel(max(logging.WARNING, logging.getLogger(name).level))
