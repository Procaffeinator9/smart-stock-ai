import threading
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends

from app.analytics.overview import build_overview_for
from app.api.v1.overview_schemas import OverviewResponse
from app.data.dataset import RetailDataset
from app.data.repository import Repository, get_dataset, get_repository

router = APIRouter(tags=["overview"])

_CACHE_KEY = "overview"
_compute_lock = threading.Lock()  # CPU-only (~0.2 s for the full dataset); keeps concurrent first requests to one computation


def cached_overview(dataset: RetailDataset) -> dict[str, Any] | None:
    """Overview metrics for this data snapshot, computed once.

    The cache lives on the dataset object, so it is invalidated automatically when the repository
    loads a new snapshot (changed CSV files or a Databricks refresh).
    """
    with _compute_lock:
        if _CACHE_KEY not in dataset._cache:
            overview = build_overview_for(dataset)
            if overview is not None:
                overview.pop("products")  # the search palette's index is not part of this response
            dataset._cache[_CACHE_KEY] = overview
        return dataset._cache[_CACHE_KEY]


@router.get("/overview", response_model=OverviewResponse, summary="Overview dashboard metrics")
def get_overview(
    dataset: RetailDataset = Depends(get_dataset),
    repository: Repository = Depends(get_repository),
):
    """KPIs, daily series, alerts, purchase orders, store health, and a baseline forecast for the
    loaded data snapshot, plus per-request freshness.

    ``meta.as_of`` is the latest inventory snapshot date in the data, not today's date. Returns
    ``status: "empty"`` when there is nothing to summarise. While the first Databricks snapshot is
    still loading, responds 503 with ``Retry-After`` (like every data endpoint).
    """
    freshness = asdict(repository.freshness())
    overview = cached_overview(dataset)
    if overview is None:
        return {
            "status": "empty",
            "freshness": freshness,
            "source": dataset.source,
            "reason": "The data source has no inventory snapshots, sales, or products to summarise.",
        }
    return {"status": "ok", "freshness": freshness, **overview}
