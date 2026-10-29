from collections import Counter
from dataclasses import asdict, dataclass
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query

from app.analytics.replenishment import ACTIONS, PRIORITIES, SETTINGS, plan_for, recommendations
from app.api.v1.common import (
    PageParams,
    SearchQuery,
    SortOrder,
    contains,
    page_params,
    paginate,
    require_choice,
    require_known,
    sort_items,
)
from app.api.v1.replenishment_schemas import Action, Priority, RecommendationPage, ReplenishmentPlanResponse
from app.data.dataset import RetailDataset
from app.data.repository import DataSourceUnavailableError, Repository, get_dataset, get_repository

router = APIRouter(prefix="/replenishment", tags=["replenishment"])

ReplenishmentSort = Literal[
    "priority", "run_out_date", "order_cost", "quantity", "days_of_cover", "demand_per_day", "product_name", "supplier_name"
]
SORT_KEYS = {
    "product_name": lambda r: r["product_name"].lower(),
    "supplier_name": lambda r: r["supplier_name"].lower(),
}
NO_SNAPSHOT = "The data source has no inventory snapshots to plan replenishment from."
NOTICE = "Simulation only: no purchase orders are created. Review every line before ordering."


@dataclass(frozen=True)
class Scope:
    store_id: str | None
    category: str | None
    supplier_id: str | None
    search: str | None

    def matches(self, row: dict[str, Any]) -> bool:
        return (
            (self.store_id is None or row["store_id"] == self.store_id)
            and (self.category is None or row["category"] == self.category)
            and (self.supplier_id is None or row["supplier_id"] == self.supplier_id)
            and contains(self.search, row["product_name"], row["sku"], row["product_id"])
        )


def scope_filters(
    dataset: RetailDataset = Depends(get_dataset),
    store_id: str | None = None,
    category: str | None = None,
    supplier_id: str | None = None,
    search: SearchQuery = None,
) -> Scope:
    require_choice("store_id", store_id, dataset.stores)
    require_choice("category", category, dataset.categories)
    require_known("supplier_id", supplier_id, dataset.supplier_by_id)
    return Scope(store_id, category, supplier_id, search)


def _counts(
    rows: list[dict[str, Any]], action: list[str] | None = None, priority: list[str] | None = None
) -> dict[str, dict[str, int]]:
    """Facet counts: priorities for the action filter, actions for the priority filter (each ignores its own)."""
    priorities = Counter(r["priority"] for r in rows if not action or r["action"] in action)
    actions = Counter(r["action"] for r in rows if not priority or r["priority"] in priority)
    return {"by_priority": {p: priorities[p] for p in PRIORITIES}, "by_action": {a: actions[a] for a in ACTIONS}}


def _facets(dataset: RetailDataset) -> dict[str, Any]:
    return {
        "stores": dataset.stores,
        "categories": dataset.categories,
        "suppliers": [
            {"supplier_id": s.supplier_id, "supplier_name": s.supplier_name}
            for s in sorted(dataset.suppliers, key=lambda s: (s.supplier_name.lower(), s.supplier_id))
        ],
    }


@router.get("", response_model=RecommendationPage, summary="Replenishment recommendations")
def list_recommendations(
    dataset: RetailDataset = Depends(get_dataset),
    scope: Scope = Depends(scope_filters),
    paging: PageParams = Depends(page_params),
    action: Annotated[list[Action] | None, Query(description="Repeat to match several; default: all actions")] = None,
    priority: Annotated[list[Priority] | None, Query(description="Repeat to match several")] = None,
    sort: ReplenishmentSort = "priority",
    order: SortOrder = "asc",
):
    """Positions that need an order (``order``), an overdue or late open order chased (``expedite``),
    or watching (``watch``), with the recommended quantity and the calculation behind it.

    Read-only. Search matches product name, SKU or product ID. ``counts.by_priority`` respects the
    action filter and ``counts.by_action`` the priority filter; each ignores its own. Default order:
    most urgent first (priority, then earliest projected run-out).
    Rows without a value for the sort field go last.
    """
    if dataset.as_of is None:
        raise DataSourceUnavailableError(NO_SNAPSHOT)
    scoped = [r for r in recommendations(dataset) if scope.matches(r)]
    rows = [r for r in scoped if (not action or r["action"] in action) and (not priority or r["priority"] in priority)]
    if sort != "priority":
        rows = sort_items(rows, SORT_KEYS.get(sort) or (lambda r: r[sort]), order)
    elif order == "desc":
        rows = list(reversed(rows))
    return {
        **paginate(rows, paging),
        "source": dataset.source,
        "as_of": dataset.as_of,
        "counts": _counts(scoped, action, priority),
        "facets": _facets(dataset),
        "settings": SETTINGS,
    }


@router.get("/plan", response_model=ReplenishmentPlanResponse, summary="Simulated reorder plan")
def get_plan(
    dataset: RetailDataset = Depends(get_dataset),
    repository: Repository = Depends(get_repository),
    scope: Scope = Depends(scope_filters),
):
    """Every recommended order line (action ``order`` with a quantity) for the filters given,
    grouped by supplier with units and estimated cost, plus counts by priority and action.

    A simulation: nothing is ordered and nothing is written. Returns ``status: "empty"`` when the
    data has no inventory snapshot.
    """
    freshness = asdict(repository.freshness())
    if dataset.as_of is None:
        return {"status": "empty", "freshness": freshness, "source": dataset.source, "reason": NO_SNAPSHOT}
    scoped = [r for r in recommendations(dataset) if scope.matches(r)]
    return {
        "status": "ok",
        "freshness": freshness,
        "source": dataset.source,
        "as_of": dataset.as_of,
        "simulation": True,
        "notice": NOTICE,
        "settings": SETTINGS,
        "counts": _counts(scoped),
        "plan": plan_for(scoped),
    }
