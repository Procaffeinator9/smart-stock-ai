from dataclasses import asdict
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.data.repository import Repository, get_repository

router = APIRouter(tags=["data source"])


class DataSourceStatus(BaseModel):
    source: Literal["csv", "databricks"]
    loaded_at: datetime | None
    age_seconds: float | None
    stale: bool
    refreshing: bool
    last_error: str | None
    last_error_at: datetime | None
    next_retry_in_seconds: float | None


@router.get("/data-source", response_model=DataSourceStatus, summary="Freshness of the cached data")
def data_source_status(repository: Repository = Depends(get_repository)):
    """Reports cache state only. It never triggers a load or contacts the data source."""
    return asdict(repository.freshness())
