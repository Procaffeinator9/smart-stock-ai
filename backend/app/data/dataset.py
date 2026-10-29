"""In-memory, read-only snapshot of the five retail tables plus lookup indexes."""

from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from typing import Literal

from app.synthetic.generator import InventorySnapshot, Product, PurchaseOrder, Sale, Supplier

DataSourceName = Literal["csv", "databricks"]


@dataclass(frozen=True)
class RetailDataset:
    source: DataSourceName
    suppliers: list[Supplier]
    products: list[Product]
    sales: list[Sale]
    inventory: list[InventorySnapshot]
    purchase_orders: list[PurchaseOrder]
    # Derived values (inventory positions per snapshot date) are memoised here.
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    @cached_property
    def supplier_by_id(self) -> dict[str, Supplier]:
        return {s.supplier_id: s for s in self.suppliers}

    @cached_property
    def product_by_id(self) -> dict[str, Product]:
        return {p.product_id: p for p in self.products}

    @cached_property
    def stores(self) -> list[str]:
        return sorted({s.store_id for s in self.inventory})

    @cached_property
    def categories(self) -> list[str]:
        return sorted({p.category for p in self.products})

    @cached_property
    def snapshot_dates(self) -> list[date]:
        return sorted({s.snapshot_date for s in self.inventory})

    @property
    def as_of(self) -> date | None:
        """The latest inventory snapshot date, used as "today" for the dataset."""
        return self.snapshot_dates[-1] if self.snapshot_dates else None
