"""Shared helpers for the read-only list endpoints: pagination, sorting, and query validation."""

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Generic, Literal, TypeVar

from fastapi import HTTPException, Query
from pydantic import BaseModel, PlainSerializer

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
MAX_SEARCH_LENGTH = 100

SortOrder = Literal["asc", "desc"]
SearchQuery = Annotated[
    str | None,
    Query(max_length=MAX_SEARCH_LENGTH, description="Case-insensitive substring match"),
]

# Money stays exact internally and is sent to clients as a JSON number.
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


@dataclass(frozen=True)
class PageParams:
    page: int
    page_size: int


def page_params(
    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="Items per page")] = DEFAULT_PAGE_SIZE,
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    total_pages: int


def paginate(items: Sequence[Any], params: PageParams, convert: Callable[[Any], Any] = lambda x: x) -> dict[str, Any]:
    """Slice one page. A page past the end returns no items (not an error)."""
    start = (params.page - 1) * params.page_size
    return {
        "items": [convert(item) for item in items[start : start + params.page_size]],
        "page": params.page,
        "page_size": params.page_size,
        "total": len(items),
        "total_pages": math.ceil(len(items) / params.page_size),
    }


def sort_items(items: Iterable[T], key: Callable[[T], Any], order: SortOrder) -> list[T]:
    """Stable sort; items whose key is None always go last, whichever the direction."""
    present, missing = [], []
    for item in items:
        (missing if key(item) is None else present).append(item)
    return sorted(present, key=key, reverse=order == "desc") + missing


def contains(query: str | None, *fields: str) -> bool:
    if not query:
        return True
    needle = query.strip().lower()
    return any(needle in field.lower() for field in fields)


def invalid_query(param: str, message: str) -> HTTPException:
    """422 in the same shape FastAPI uses for its own validation errors."""
    return HTTPException(status_code=422, detail=[{"type": "value_error", "loc": ["query", param], "msg": message}])


def require_choice(param: str, value: str | None, allowed: Sequence[str]) -> None:
    if value is not None and value not in allowed:
        raise invalid_query(param, f"Unknown {param} '{value}'. Expected one of: {', '.join(allowed)}")


def require_known(param: str, value: str | None, known: Iterable[str]) -> None:
    """For identifiers, where listing every allowed value would be too long."""
    if value is not None and value not in known:
        raise invalid_query(param, f"Unknown {param} '{value}'")


def require_date_order(date_from: date | None, date_to: date | None) -> None:
    if date_from and date_to and date_from > date_to:
        raise invalid_query("date_from", "date_from must be on or before date_to")
