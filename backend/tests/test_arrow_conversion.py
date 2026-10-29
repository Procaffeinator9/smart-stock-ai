"""Arrow result path: real pyarrow tables with the DDL's types, converted by the connector's own
ResultSet._convert_arrow_table, must reproduce the generator's records through the strict
conversion layer. Skipped when pyarrow is not installed (the row-based fallback is covered by
test_databricks_repository.py). Nothing connects."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

pa = pytest.importorskip("pyarrow")

from databricks.sql.result_set import ResultSet  # noqa: E402

from app.data.conversion import convert_rows, validate_relations  # noqa: E402
from app.synthetic import GeneratorConfig, generate_dataset  # noqa: E402
from app.synthetic.loader import TABLE_SPECS, Column  # noqa: E402

SMALL = GeneratorConfig(seed=21, num_suppliers=4, num_products=16, num_stores=2, num_days=12)

# Arrow types a Databricks SQL warehouse uses for the DDL column types (TIMESTAMP is an instant).
_SIMPLE = {"STRING": pa.string(), "INT": pa.int32(), "BOOLEAN": pa.bool_(), "DATE": pa.date32()}


def arrow_type(column: Column, timestamp_tz: str | None):
    if column.sql_type.startswith("DECIMAL("):
        precision, scale = (int(x) for x in column.sql_type[8:-1].split(","))
        return pa.decimal128(precision, scale)
    if column.sql_type == "TIMESTAMP":
        return pa.timestamp("us", tz=timestamp_tz)
    return _SIMPLE[column.sql_type]


def to_arrow(spec, records, timestamp_tz: str | None) -> "pa.Table":
    arrays = {}
    for column in spec.columns:
        values = [getattr(record, column.name) for record in records]
        if column.sql_type == "TIMESTAMP" and timestamp_tz:
            values = [v.replace(tzinfo=UTC) if v is not None else None for v in values]
        arrays[column.name] = pa.array(values, type=arrow_type(column, timestamp_tz))
    return pa.table(arrays)


def connector_rows(table, disable_pandas: bool) -> list:
    """Rows exactly as the connector's Arrow fetch path builds them."""
    fake_result_set = SimpleNamespace(
        description=[(name, None, None, None, None, None, None) for name in table.column_names],
        connection=SimpleNamespace(disable_pandas=disable_pandas),
    )
    return ResultSet._convert_arrow_table(fake_result_set, table)


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(SMALL)


@pytest.mark.parametrize("disable_pandas", [True, False], ids=["as_py-path", "pandas-path"])
@pytest.mark.parametrize("timestamp_tz", ["Etc/UTC", None], ids=["tz-aware-timestamps", "naive-timestamps"])
def test_arrow_results_convert_to_identical_records(dataset, disable_pandas: bool, timestamp_tz) -> None:
    tables = {}
    for spec in TABLE_SPECS:
        records = dataset.tables()[spec.name]
        rows = connector_rows(to_arrow(spec, records, timestamp_tz), disable_pandas)
        errors: list[str] = []
        converted = convert_rows(spec, rows, errors)
        assert errors == [], errors[:3]
        assert [type(records[0])(**row) for row in converted] == records, spec.name
        tables[spec.name] = converted
    validate_relations(tables)  # constraints, keys, and foreign keys still pass


def test_arrow_values_are_plain_python_types(dataset) -> None:
    spec = next(s for s in TABLE_SPECS if s.name == "purchase_orders")
    rows = connector_rows(to_arrow(spec, dataset.purchase_orders, "Etc/UTC"), disable_pandas=True)
    types = {name: {type(row[i]).__name__ for row in rows} for i, name in enumerate(spec.column_names)}
    assert types["order_date"] == {"date"}
    assert types["unit_cost"] == {"Decimal"}
    assert types["quantity_ordered"] == {"int"}
    assert types["actual_delivery_date"] <= {"date", "NoneType"} and "NoneType" in types["actual_delivery_date"]
    products = next(s for s in TABLE_SPECS if s.name == "products")
    product_rows = connector_rows(to_arrow(products, dataset.products, "Etc/UTC"), disable_pandas=True)
    created = {row[products.column_names.index("created_at")] for row in product_rows}
    assert all(isinstance(v, datetime) and v.tzinfo is not None for v in created)  # converted to naive UTC later
