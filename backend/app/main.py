import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.v1.router import api_router
from app.core.config import DatabricksSettings, get_settings
from app.core.log_redaction import install_secret_redaction
from app.data.repository import DataSourceUnavailableError, get_repository

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.data_source == "csv":
        # Load and validate the CSVs in the background so the first request is fast. Never done
        # for Databricks, so starting the API does not query the warehouse.
        def warm_up() -> None:
            try:
                get_repository(settings).dataset()
            except DataSourceUnavailableError as exc:
                logger.warning("CSV data source not ready: %s", exc)

        threading.Thread(target=warm_up, name="csv-warm-up", daemon=True).start()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Redact Databricks secrets from all log output, including the connector's own loggers.
    # A fresh settings object, so the cached get_databricks_settings() is not pinned here.
    install_secret_redaction(DatabricksSettings())

    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api/v1")

    @app.exception_handler(DataSourceUnavailableError)
    async def data_source_unavailable(_: Request, exc: DataSourceUnavailableError) -> JSONResponse:
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        return JSONResponse(status_code=503, content={"detail": str(exc)}, headers=headers)

    return app


app = create_app()
