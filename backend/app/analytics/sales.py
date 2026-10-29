"""Sales analytics for a date window and filters, calculated from the loaded dataset.

Definitions (also shown on the Sales page):

- revenue          = quantity_sold × unit_selling_price, summed
- gross margin     = revenue − quantity_sold × the product's unit cost. The data has one standard
                     cost per product (the same cost used on purchase orders), so this is margin at
                     standard cost.
- margin rate      = gross margin ÷ revenue
- average price    = revenue ÷ units
- promotion share  = promotional revenue (or units) ÷ all revenue (or units)
- average discount = 1 − promotional revenue ÷ the same units at list price
- promotion uplift = average units per sale line on promotion ÷ average units per sale line at the
                     regular price − 1, over the products promoted in the window. A sale line is one
                     store, product and day with at least one unit sold, so days without sales are
                     not counted.
- stockout days    = store-product days that ended with no available units (on hand − reserved
                     <= 0, the inventory "out of stock" status). Ignores the promotion filter.
- previous period  = the same number of days immediately before the window, or None when the
                     data does not cover all of it.

Each sale row is a daily total for one store and product, not a customer transaction, so
transactions, basket size and average order value cannot be calculated from this data.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from functools import cached_property
from typing import Any

from app.analytics.cache import memoize
from app.analytics.stock import position_status
from app.data.dataset import RetailDataset
from app.synthetic.generator import Product, Sale

CENT = Decimal("0.01")
ZERO = Decimal(0)
DEFAULT_WINDOW_DAYS = 30


@dataclass(frozen=True)
class SalesFilters:
    store_id: str | None = None
    category: str | None = None
    supplier_id: str | None = None
    promotion: bool | None = None


@dataclass(frozen=True)
class Period:
    """Inclusive date window."""

    date_from: date
    date_to: date

    @property
    def days(self) -> int:
        return (self.date_to - self.date_from).days + 1

    def dates(self) -> list[date]:
        return [self.date_from + timedelta(days=i) for i in range(self.days)]

    def previous(self) -> "Period":
        """The same number of days immediately before this window."""
        return Period(self.date_from - timedelta(days=self.days), self.date_from - timedelta(days=1))

    def as_dict(self) -> dict[str, Any]:
        return {"date_from": self.date_from, "date_to": self.date_to, "days": self.days}


@dataclass
class Totals:
    revenue: Decimal = ZERO
    cost: Decimal = ZERO
    units: int = 0
    lines: int = 0
    promo_revenue: Decimal = ZERO
    promo_units: int = 0
    promo_lines: int = 0
    promo_list_value: Decimal = ZERO  # promotional units at list price

    @property
    def margin(self) -> Decimal:
        return self.revenue - self.cost

    def add(self, sale: Sale, revenue: Decimal, cost: Decimal, list_value: Decimal) -> None:
        self.revenue += revenue
        self.cost += cost
        self.units += sale.quantity_sold
        self.lines += 1
        if sale.promotion_applied:
            self.promo_revenue += revenue
            self.promo_units += sale.quantity_sold
            self.promo_lines += 1
            self.promo_list_value += list_value

    def merge(self, other: "Totals") -> None:
        self.revenue += other.revenue
        self.cost += other.cost
        self.units += other.units
        self.lines += other.lines
        self.promo_revenue += other.promo_revenue
        self.promo_units += other.promo_units
        self.promo_lines += other.promo_lines
        self.promo_list_value += other.promo_list_value


@dataclass
class WindowSales:
    """Aggregates for one window and filter set. Every product, category and store in scope has an
    entry, including those with no sales."""

    period: Period
    daily: list[Totals]
    by_product: dict[str, Totals]
    by_category: dict[str, Totals]
    by_store: dict[str, Totals]
    stores_sold: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    stockout_days: Counter[str] = field(default_factory=Counter)  # by product

    @cached_property
    def total(self) -> Totals:
        total = Totals()
        for totals in self.by_product.values():
            total.merge(totals)
        return total


# --- Indexes (built once per data snapshot) ----------------------------------------------------


def _sales_by_date(dataset: RetailDataset) -> dict[date, list[Sale]]:
    def build() -> dict[date, list[Sale]]:
        index: dict[date, list[Sale]] = defaultdict(list)
        for sale in dataset.sales:
            index[sale.sale_date].append(sale)
        return dict(index)

    return memoize(dataset, "sales_index", "by_date", build)


def _stockouts_by_date(dataset: RetailDataset) -> dict[date, list[tuple[str, str]]]:
    def build() -> dict[date, list[tuple[str, str]]]:
        index: dict[date, list[tuple[str, str]]] = defaultdict(list)
        for snap in dataset.inventory:
            if position_status(snap) == "out_of_stock":
                index[snap.snapshot_date].append((snap.store_id, snap.product_id))
        return dict(index)

    return memoize(dataset, "sales_index", "stockouts_by_date", build)


def sales_bounds(dataset: RetailDataset) -> Period | None:
    """First and last sale date in the data, or None when there are no sales."""
    index = _sales_by_date(dataset)
    return Period(min(index), max(index)) if index else None


def previous_period(period: Period, bounds: Period) -> Period | None:
    previous = period.previous()
    return previous if previous.date_from >= bounds.date_from else None


def products_in_scope(dataset: RetailDataset, filters: SalesFilters) -> list[Product]:
    return [
        p
        for p in dataset.products
        if (filters.category is None or p.category == filters.category)
        and (filters.supplier_id is None or p.supplier_id == filters.supplier_id)
    ]


# --- Aggregation -------------------------------------------------------------------------------


def window_sales(dataset: RetailDataset, period: Period, filters: SalesFilters) -> WindowSales:
    """Aggregates for this window and filters, cached per data snapshot."""
    return memoize(dataset, "sales_windows", (period, filters), lambda: _window_sales(dataset, period, filters))


def _window_sales(dataset: RetailDataset, period: Period, filters: SalesFilters) -> WindowSales:
    scope = {p.product_id: p for p in products_in_scope(dataset, filters)}
    stores = [filters.store_id] if filters.store_id is not None else dataset.stores
    window = WindowSales(
        period=period,
        daily=[Totals() for _ in range(period.days)],
        by_product={pid: Totals() for pid in scope},
        by_category={c: Totals() for c in sorted({p.category for p in scope.values()})},
        by_store={s: Totals() for s in stores},
    )
    sales = _sales_by_date(dataset)
    stockouts = _stockouts_by_date(dataset)

    for offset, day in enumerate(period.dates()):
        day_totals = window.daily[offset]
        for sale in sales.get(day, ()):
            product = scope.get(sale.product_id)
            if (
                product is None
                or (filters.store_id is not None and sale.store_id != filters.store_id)
                or (filters.promotion is not None and sale.promotion_applied != filters.promotion)
            ):
                continue
            revenue = sale.unit_selling_price * sale.quantity_sold
            cost = product.unit_cost * sale.quantity_sold
            list_value = product.selling_price * sale.quantity_sold if sale.promotion_applied else ZERO
            for totals in (
                day_totals,
                window.by_product[product.product_id],
                window.by_category[product.category],
                window.by_store.setdefault(sale.store_id, Totals()),
            ):
                totals.add(sale, revenue, cost, list_value)
            window.stores_sold[product.product_id].add(sale.store_id)
        for store_id, product_id in stockouts.get(day, ()):
            if product_id in scope and (filters.store_id is None or store_id == filters.store_id):
                window.stockout_days[product_id] += 1
    return window


# --- Response builders -------------------------------------------------------------------------


def _money(value: Decimal) -> float:
    return float(value.quantize(CENT))


def _ratio(numerator: Decimal | int, denominator: Decimal | int, digits: int = 4) -> float | None:
    return round(float(numerator) / float(denominator), digits) if denominator else None


def _change(current: Decimal, previous: Decimal | None) -> float | None:
    """Relative change, or None without a previous value to compare with."""
    return _ratio(current - previous, previous) if previous else None


def _totals_out(window: WindowSales) -> dict[str, Any]:
    total = window.total
    return {
        "revenue": _money(total.revenue),
        "units": total.units,
        "gross_margin": _money(total.margin),
        "margin_rate": _ratio(total.margin, total.revenue),
        "avg_unit_price": _money(total.revenue / total.units) if total.units else None,
        "sale_lines": total.lines,
        "products_sold": sum(1 for t in window.by_product.values() if t.units),
        "promo_revenue": _money(total.promo_revenue),
        "promo_units": total.promo_units,
        "promo_revenue_share": _ratio(total.promo_revenue, total.revenue),
        "promo_units_share": _ratio(total.promo_units, total.units),
        "stockout_days": sum(window.stockout_days.values()),
    }


def _breakdown(key: str, groups: dict[str, Totals], previous: dict[str, Totals] | None, grand: Decimal) -> list[dict]:
    rows = []
    for name, totals in groups.items():
        before = previous[name].revenue if previous is not None and name in previous else None
        rows.append(
            {
                key: name,
                "revenue": _money(totals.revenue),
                "units": totals.units,
                "gross_margin": _money(totals.margin),
                "margin_rate": _ratio(totals.margin, totals.revenue),
                "share": _ratio(totals.revenue, grand) or 0.0,
                "previous_revenue": _money(before) if before is not None else None,
                "change": _change(totals.revenue, before),
            }
        )
    return rows


def _promotion(window: WindowSales) -> dict[str, Any]:
    total = window.total
    promoted = [t for t in window.by_product.values() if t.promo_lines]
    promo_lines = sum(t.promo_lines for t in promoted)
    promo_units = sum(t.promo_units for t in promoted)
    regular_lines = sum(t.lines - t.promo_lines for t in promoted)
    regular_units = sum(t.units - t.promo_units for t in promoted)
    per_line_promo = promo_units / promo_lines if promo_lines else None
    per_line_regular = regular_units / regular_lines if regular_lines else None
    return {
        "promo_revenue": _money(total.promo_revenue),
        "promo_units": total.promo_units,
        "promo_lines": total.promo_lines,
        "revenue_share": _ratio(total.promo_revenue, total.revenue),
        "units_share": _ratio(total.promo_units, total.units),
        "avg_discount": _ratio(total.promo_list_value - total.promo_revenue, total.promo_list_value),
        "promoted_products": len(promoted),
        "units_per_line_promo": round(per_line_promo, 2) if per_line_promo is not None else None,
        "units_per_line_regular": round(per_line_regular, 2) if per_line_regular is not None else None,
        "uplift": round(per_line_promo / per_line_regular - 1, 4) if per_line_promo and per_line_regular else None,
    }


def sales_summary(dataset: RetailDataset, period: Period, filters: SalesFilters, bounds: Period) -> dict[str, Any]:
    """KPIs (with the previous period), daily series, category and store breakdowns, promotions."""
    current = window_sales(dataset, period, filters)
    prior = previous_period(period, bounds)
    previous = window_sales(dataset, prior, filters) if prior else None
    grand = current.total.revenue
    return {
        "period": period.as_dict(),
        "previous_period": prior.as_dict() if prior else None,
        "kpis": {"current": _totals_out(current), "previous": _totals_out(previous) if previous else None},
        "daily": {
            "dates": period.dates(),
            "revenue": [_money(t.revenue) for t in current.daily],
            "units": [t.units for t in current.daily],
            "gross_margin": [_money(t.margin) for t in current.daily],
            "promo_revenue": [_money(t.promo_revenue) for t in current.daily],
        },
        "by_category": sorted(
            _breakdown("category", current.by_category, previous.by_category if previous else None, grand),
            key=lambda r: (-r["revenue"], r["category"]),
        ),
        "by_store": _breakdown("store_id", current.by_store, previous.by_store if previous else None, grand),
        "promotion": _promotion(current),
    }


def product_performance(
    dataset: RetailDataset, period: Period, filters: SalesFilters, bounds: Period
) -> list[dict[str, Any]]:
    """One row per product in scope (including products with no sales), in product ID order."""
    current = window_sales(dataset, period, filters)
    prior = previous_period(period, bounds)
    previous = window_sales(dataset, prior, filters) if prior else None
    grand = current.total.revenue
    rows = []
    for product in products_in_scope(dataset, filters):
        totals = current.by_product[product.product_id]
        before = previous.by_product[product.product_id].revenue if previous else None
        rows.append(
            {
                "product_id": product.product_id,
                "product_name": product.product_name,
                "sku": product.sku,
                "category": product.category,
                "supplier_id": product.supplier_id,
                "supplier_name": dataset.supplier_by_id[product.supplier_id].supplier_name,
                "revenue": _money(totals.revenue),
                "units": totals.units,
                "gross_margin": _money(totals.margin),
                "margin_rate": _ratio(totals.margin, totals.revenue),
                "avg_unit_price": _money(totals.revenue / totals.units) if totals.units else None,
                "revenue_share": _ratio(totals.revenue, grand),
                "promo_revenue_share": _ratio(totals.promo_revenue, totals.revenue),
                "stores_sold": len(current.stores_sold.get(product.product_id, ())),
                "stockout_days": current.stockout_days[product.product_id],
                "previous_revenue": _money(before) if before is not None else None,
                "revenue_change": _change(totals.revenue, before),
            }
        )
    return rows
