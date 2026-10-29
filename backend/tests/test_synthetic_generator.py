import csv
import dataclasses
import hashlib
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.synthetic import GeneratorConfig, generate_dataset, write_csv

SMALL = GeneratorConfig(seed=7, num_suppliers=5, num_products=24, num_stores=2, num_days=30)


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(SMALL)


def _digest(directory: Path) -> str:
    sha = hashlib.sha256()
    for path in sorted(directory.glob("*.csv")):
        sha.update(path.name.encode())
        sha.update(path.read_bytes())
    return sha.hexdigest()


def test_same_seed_produces_identical_csv_output(tmp_path: Path) -> None:
    write_csv(generate_dataset(SMALL), tmp_path / "a")
    write_csv(generate_dataset(SMALL), tmp_path / "b")

    assert _digest(tmp_path / "a") == _digest(tmp_path / "b")


def test_different_seed_produces_different_data(dataset) -> None:
    other = generate_dataset(dataclasses.replace(SMALL, seed=8))

    assert other.products != dataset.products
    assert other.sales != dataset.sales


def test_row_counts_follow_config(dataset) -> None:
    assert len(dataset.suppliers) == SMALL.num_suppliers
    assert len(dataset.products) == SMALL.num_products
    # One end-of-day snapshot per store, product, and day.
    assert len(dataset.inventory) == SMALL.num_stores * SMALL.num_products * SMALL.num_days
    assert dataset.sales, "expected some sales"
    assert dataset.purchase_orders, "expected some replenishment orders"


def test_primary_keys_are_unique(dataset) -> None:
    for table, records in dataset.tables().items():
        key = dataclasses.fields(records[0])[0].name
        ids = [getattr(r, key) for r in records]
        assert len(ids) == len(set(ids)), f"duplicate {key} in {table}"


def test_foreign_keys_resolve(dataset) -> None:
    supplier_ids = {s.supplier_id for s in dataset.suppliers}
    product_ids = {p.product_id for p in dataset.products}
    stores = set(dataset.stores)

    assert {p.supplier_id for p in dataset.products} <= supplier_ids
    assert {s.product_id for s in dataset.sales} <= product_ids
    assert {i.product_id for i in dataset.inventory} <= product_ids
    assert {po.product_id for po in dataset.purchase_orders} <= product_ids
    assert {po.supplier_id for po in dataset.purchase_orders} <= supplier_ids
    assert {r.store_id for r in [*dataset.sales, *dataset.inventory, *dataset.purchase_orders]} <= stores


def test_purchase_orders_use_the_product_supplier(dataset) -> None:
    supplier_of = {p.product_id: p.supplier_id for p in dataset.products}
    assert all(po.supplier_id == supplier_of[po.product_id] for po in dataset.purchase_orders)


def test_one_inventory_snapshot_per_store_product_day(dataset) -> None:
    keys = Counter((i.snapshot_date, i.store_id, i.product_id) for i in dataset.inventory)
    assert set(keys.values()) == {1}


def test_values_satisfy_check_constraints(dataset) -> None:
    """Mirrors databricks/sql/06_add_check_constraints.sql so generated data will load."""
    for s in dataset.suppliers:
        assert s.lead_time_days > 0 and s.minimum_order_quantity > 0
        assert Decimal(0) <= s.reliability_score <= Decimal(1)
        assert s.contact_email.endswith(".example.com")
    for p in dataset.products:
        assert p.unit_cost >= 0 and p.selling_price > p.unit_cost
        assert p.shelf_life_days is None or p.shelf_life_days > 0
        assert p.created_at.date() < SMALL.start_date
    for s in dataset.sales:
        assert s.quantity_sold > 0 and s.unit_selling_price > 0
        assert SMALL.start_date <= s.sale_date <= SMALL.end_date
    for i in dataset.inventory:
        assert i.quantity_on_hand >= 0 and 0 <= i.quantity_reserved <= i.quantity_on_hand
        assert i.reorder_point >= 0 and i.safety_stock >= 0
    for po in dataset.purchase_orders:
        assert po.quantity_ordered > 0 and po.unit_cost >= 0
        assert po.order_status in {"PLACED", "IN_TRANSIT", "DELIVERED", "CANCELLED"}
        assert po.expected_delivery_date >= po.order_date
        assert (po.order_status == "DELIVERED") == (po.actual_delivery_date is not None)
        if po.actual_delivery_date is not None:
            assert po.order_date <= po.actual_delivery_date <= SMALL.end_date


def test_promotional_sales_are_discounted(dataset) -> None:
    price_of = {p.product_id: p.selling_price for p in dataset.products}
    for sale in dataset.sales:
        if sale.promotion_applied:
            assert sale.unit_selling_price < price_of[sale.product_id]
        else:
            assert sale.unit_selling_price == price_of[sale.product_id]


def test_inventory_balances_with_sales_and_deliveries(dataset) -> None:
    """Day-over-day stock change equals deliveries received minus units sold."""
    sold = Counter()
    for s in dataset.sales:
        sold[(s.sale_date, s.store_id, s.product_id)] += s.quantity_sold
    received = Counter()
    for po in dataset.purchase_orders:
        if po.actual_delivery_date is not None:
            received[(po.actual_delivery_date, po.store_id, po.product_id)] += po.quantity_ordered

    on_hand = {(i.snapshot_date, i.store_id, i.product_id): i.quantity_on_hand for i in dataset.inventory}
    for (day, store, product), quantity in on_hand.items():
        if day == SMALL.start_date:
            continue
        previous = on_hand[(date.fromordinal(day.toordinal() - 1), store, product)]
        assert quantity == previous + received[(day, store, product)] - sold[(day, store, product)]


def test_write_csv_headers_and_round_trip(dataset, tmp_path: Path) -> None:
    paths = write_csv(dataset, tmp_path)

    assert set(paths) == {"suppliers", "products", "sales", "inventory", "purchase_orders"}
    with paths["purchase_orders"].open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(dataset.purchase_orders)
    assert list(rows[0]) == [f.name for f in dataclasses.fields(dataset.purchase_orders[0])]
    with paths["sales"].open(encoding="utf-8", newline="") as handle:
        assert next(csv.DictReader(handle))["promotion_applied"] in {"true", "false"}


def test_invalid_config_rejected() -> None:
    with pytest.raises(ValueError):
        GeneratorConfig(num_products=0)
