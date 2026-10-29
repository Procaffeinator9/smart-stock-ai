"""Static checks on databricks/sql/*.sql. Nothing here connects to Databricks."""

import dataclasses
import re
from pathlib import Path

import pytest

from app.synthetic import TABLE_RECORD_TYPES

SQL_DIR = Path(__file__).resolve().parents[2] / "databricks" / "sql"
SCHEMA = "workspace.smartstock_retail"

CREATE_RE = re.compile(rf"CREATE TABLE IF NOT EXISTS {re.escape(SCHEMA)}\.(\w+) \((.*?)\n\)", re.S)
COLUMN_RE = re.compile(r"^  (\w+)\s+(STRING|INT|BIGINT|BOOLEAN|DATE|TIMESTAMP|DECIMAL\(\d+,\d+\))(?=\s)", re.M)


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _strip_string_literals(sql: str) -> str:
    return re.sub(r"'[^']*'", "''", sql)


def _sql_files() -> list[Path]:
    return sorted(SQL_DIR.glob("*.sql"))


def _ddl_columns() -> dict[str, list[str]]:
    tables = {}
    for path in _sql_files():
        for name, body in CREATE_RE.findall(path.read_text(encoding="utf-8")):
            tables[name] = [column for column, _ in COLUMN_RE.findall(body)]
    return tables


def test_every_table_has_a_create_script() -> None:
    assert set(_ddl_columns()) == set(TABLE_RECORD_TYPES)


@pytest.mark.parametrize("table", list(TABLE_RECORD_TYPES))
def test_ddl_columns_match_generator(table: str) -> None:
    expected = [f.name for f in dataclasses.fields(TABLE_RECORD_TYPES[table])]
    assert _ddl_columns()[table] == expected


@pytest.mark.parametrize("path", _sql_files(), ids=lambda p: p.name)
def test_scripts_are_non_destructive(path: Path) -> None:
    sql = _strip_comments(path.read_text(encoding="utf-8")).upper()
    for forbidden in (
        "CREATE OR REPLACE",
        "DROP TABLE",
        "DROP SCHEMA",
        "DROP CATALOG",
        "CREATE CATALOG",
        "CREATE SCHEMA",
        "TRUNCATE",
        "INSERT ",
        "MERGE ",
        "DELETE ",
        "UPDATE ",
        "LOCATION",
    ):
        assert forbidden not in sql, f"{path.name} contains {forbidden!r}"


@pytest.mark.parametrize("path", _sql_files(), ids=lambda p: p.name)
def test_table_references_are_fully_qualified(path: Path) -> None:
    sql = _strip_string_literals(_strip_comments(path.read_text(encoding="utf-8")))
    refs = re.findall(r"\b(?:TABLE(?: IF NOT EXISTS)?|REFERENCES|TBLPROPERTIES)\s+([\w.`]+)", sql, re.I)
    for ref in refs:
        assert ref.startswith(f"{SCHEMA}."), f"{path.name}: {ref} is not fully qualified"


@pytest.mark.parametrize("path", _sql_files(), ids=lambda p: p.name)
def test_scripts_contain_no_credentials(path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    assert not re.search(r"dapi[0-9a-f]{20,}", sql, re.I)
    assert not re.search(r"(?i)(token|password|secret)\s*=", sql)
