from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import __version__
from app.core.config import DatabricksSettings, Settings, get_databricks_settings, get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str
    # Whether the DATABRICKS_* variables are set. This does NOT mean a connection has been tested.
    databricks_configured: bool
    # Where the data API reads from (configuration only; the source is not touched by this check).
    data_source: Literal["csv", "databricks"]


@router.get("/health", response_model=HealthResponse)
def health(
    settings: Settings = Depends(get_settings),
    databricks: DatabricksSettings = Depends(get_databricks_settings),
) -> HealthResponse:
    """Liveness check. Makes no network calls and works without Databricks credentials."""
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=__version__,
        environment=settings.environment,
        databricks_configured=databricks.is_configured,
        data_source=settings.data_source,
    )
