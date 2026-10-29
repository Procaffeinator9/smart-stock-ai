"""Read-only repositories that load the retail tables into a ``RetailDataset``.

- ``CsvRepository`` (default) reads the generated synthetic CSVs, validating them with the same
  preflight used by the Databricks loader, and reloads when the files change.
- ``DatabricksRepository`` runs SELECT-only queries against the configured catalog and schema.
  It is UNVERIFIED: it has only been tested against fake connections, never a real warehouse.

Neither repository writes anything.

Databricks refresh model (stale-while-revalidate):
- At most one refresh runs at a time, in a background thread. The shared lock is held only to
  read or update state, never during network I/O.
- A request with a cached snapshot gets it immediately, even while a refresh is running or after
  a refresh failed; freshness metadata (age, stale, last error) is exposed via ``freshness()``.
- Without any snapshot, a request waits at most ``wait_seconds`` for the first load, then gets a
  DataSourceUnavailableError (HTTP 503) with a retry hint.
- After a failure, the next attempt waits an exponential backoff (15 s doubling to 5 min), so
  waiting requests do not each retry.
"""

import logging
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from fastapi import Depends, Response

from app.core.config import DatabricksSettings, Settings, get_databricks_settings, get_settings
from app.data.conversion import ResultValidationError, convert_rows, validate_description, validate_relations
from app.data.dataset import RetailDataset
from app.db.databricks import (
    ERROR_MESSAGES,
    InvalidIdentifierError,
    classify_error,
    databricks_connection,
    qualified_table,
    sanitize_error,
)
from app.synthetic.generator import InventorySnapshot, Product, PurchaseOrder, Sale, Supplier
from app.synthetic.loader import TABLE_SPECS, PreflightError, preflight

logger = logging.getLogger(__name__)

RECORD_TYPES = {
    "suppliers": Supplier,
    "products": Product,
    "sales": Sale,
    "inventory": InventorySnapshot,
    "purchase_orders": PurchaseOrder,
}

FETCH_BATCH_ROWS = 50_000  # rows per fetchmany() call while converting
MAX_ROWS_PER_TABLE = 1_000_000  # refuse to hold anything larger in memory
BACKOFF_INITIAL_SECONDS = 15.0
BACKOFF_MAX_SECONDS = 300.0


class DataSourceUnavailableError(RuntimeError):
    """The configured data source cannot be read. The message is safe to show to API clients."""

    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True)
class Freshness:
    source: str
    loaded_at: datetime | None  # when the served snapshot was loaded (UTC)
    age_seconds: float | None
    stale: bool  # older than the refresh interval (a refresh is due or failing)
    refreshing: bool
    last_error: str | None  # client-safe category message of the most recent failed refresh
    last_error_at: datetime | None
    next_retry_in_seconds: float | None


class Repository(Protocol):
    source: str

    def dataset(self) -> RetailDataset: ...

    def freshness(self) -> Freshness: ...


def _build(source: str, tables: dict[str, list[dict]]) -> RetailDataset:
    return RetailDataset(
        source=source,  # type: ignore[arg-type]
        **{name: [RECORD_TYPES[name](**row) for row in rows] for name, rows in tables.items()},
    )


class CsvRepository:
    source = "csv"

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self._lock = threading.Lock()
        self._dataset: RetailDataset | None = None
        self._signature: tuple | None = None
        self._loaded_at: datetime | None = None

    def _file_signature(self) -> tuple:
        signature = []
        missing = []
        for spec in TABLE_SPECS:
            path = self.data_dir / f"{spec.name}.csv"
            try:
                stat = path.stat()
            except FileNotFoundError:
                missing.append(path.name)
                continue
            signature.append((path.name, stat.st_mtime_ns, stat.st_size))
        if missing:
            logger.warning("Synthetic CSVs missing in %s: %s", self.data_dir, ", ".join(missing))
            raise DataSourceUnavailableError(
                f"Synthetic CSV files are missing ({', '.join(missing)}). "
                "Generate them with: python scripts/generate_synthetic_data.py"
            )
        return tuple(signature)

    def dataset(self) -> RetailDataset:
        # Local file I/O only (no network), so loading under the lock is acceptable here.
        signature = self._file_signature()
        with self._lock:
            if self._dataset is None or signature != self._signature:
                started = time.perf_counter()
                try:
                    tables = preflight(self.data_dir)
                except PreflightError as exc:
                    logger.error("Synthetic CSV validation failed: %s", exc.errors[:5])
                    raise DataSourceUnavailableError(
                        f"Synthetic CSV files failed validation ({len(exc.errors)} problem(s)), first: {exc.errors[0]}"
                    ) from exc
                self._dataset = _build(self.source, {name: data.rows for name, data in tables.items()})
                self._signature = signature
                self._loaded_at = datetime.now(UTC)
                logger.info("Loaded synthetic CSVs in %.2fs", time.perf_counter() - started)
            return self._dataset

    def freshness(self) -> Freshness:
        with self._lock:
            loaded_at = self._loaded_at
        age = (datetime.now(UTC) - loaded_at).total_seconds() if loaded_at else None
        return Freshness("csv", loaded_at, age, False, False, None, None, None)


@dataclass(frozen=True)
class _Snapshot:
    dataset: RetailDataset
    loaded_monotonic: float
    loaded_at: datetime


@dataclass(frozen=True)
class _Failure:
    message: str  # client-safe
    at_monotonic: float
    at: datetime


def _start_daemon_thread(target: Callable[[], None]) -> None:
    threading.Thread(target=target, name="databricks-refresh", daemon=True).start()


class DatabricksRepository:
    """UNVERIFIED: SELECT-only reads with bounded waits and stale-while-revalidate caching."""

    source = "databricks"

    def __init__(
        self,
        settings: DatabricksSettings,
        *,
        refresh_seconds: float = 300,
        wait_seconds: float = 10,
        connect: Callable = databricks_connection,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        start: Callable[[Callable[[], None]], None] = _start_daemon_thread,
    ):
        self.settings = settings
        self._refresh_seconds = refresh_seconds
        self._wait_seconds = wait_seconds
        self._connect = connect
        self._clock = clock
        self._now = now
        self._start = start
        self._cond = threading.Condition()
        self._snapshot: _Snapshot | None = None
        self._refreshing = False
        self._failure: _Failure | None = None
        self._consecutive_failures = 0
        self._retry_at = 0.0

    # --- public API ---------------------------------------------------------------------------

    def dataset(self) -> RetailDataset:
        with self._cond:
            start_refresh = self._claim_refresh_locked()
        if start_refresh:
            self._start(self._refresh)  # outside the lock

        with self._cond:
            if self._snapshot is None:
                deadline = self._clock() + self._wait_seconds
                while self._snapshot is None and self._refreshing:
                    remaining = deadline - self._clock()
                    if remaining <= 0:
                        break
                    self._cond.wait(remaining)
            if self._snapshot is not None:
                return self._snapshot.dataset
            raise self._unavailable_locked()

    def freshness(self) -> Freshness:
        with self._cond:
            now = self._clock()
            snap, failure = self._snapshot, self._failure
            age = now - snap.loaded_monotonic if snap else None
            return Freshness(
                source=self.source,
                loaded_at=snap.loaded_at if snap else None,
                age_seconds=round(age, 1) if age is not None else None,
                stale=snap is not None and age >= self._refresh_seconds,
                refreshing=self._refreshing,
                last_error=failure.message if failure else None,
                last_error_at=failure.at if failure else None,
                next_retry_in_seconds=round(max(self._retry_at - now, 0), 1) if failure else None,
            )

    # --- refresh coordination -----------------------------------------------------------------

    def _claim_refresh_locked(self) -> bool:
        """Mark a refresh as running if one is due and allowed. Caller holds the lock."""
        now = self._clock()
        due = self._snapshot is None or now - self._snapshot.loaded_monotonic >= self._refresh_seconds
        if due and not self._refreshing and now >= self._retry_at:
            self._refreshing = True
            return True
        return False

    def _refresh(self) -> None:
        try:
            dataset = self._load()  # network I/O, no lock held
        except DataSourceUnavailableError as exc:
            self._record_failure(str(exc))
        except Exception as exc:  # defensive: _load already converts errors
            logger.error("Databricks refresh failed unexpectedly: %s", sanitize_error(exc, self.settings))
            self._record_failure(ERROR_MESSAGES["query"])
        else:
            with self._cond:
                self._snapshot = _Snapshot(dataset, self._clock(), self._now())
                self._failure = None
                self._consecutive_failures = 0
                self._retry_at = 0.0
                self._refreshing = False
                self._cond.notify_all()

    def _record_failure(self, message: str) -> None:
        with self._cond:
            self._consecutive_failures += 1
            backoff = min(BACKOFF_INITIAL_SECONDS * 2 ** (self._consecutive_failures - 1), BACKOFF_MAX_SECONDS)
            self._retry_at = self._clock() + backoff
            self._failure = _Failure(message, self._clock(), self._now())
            self._refreshing = False
            self._cond.notify_all()
        logger.warning("Databricks refresh failed (%s); next attempt in %.0fs", message, backoff)

    def _unavailable_locked(self) -> DataSourceUnavailableError:
        if self._refreshing:
            return DataSourceUnavailableError(
                "Databricks data is still loading. Try again shortly.", retry_after=math.ceil(self._wait_seconds) or 5
            )
        retry_after = max(1, math.ceil(self._retry_at - self._clock()))
        reason = self._failure.message if self._failure else "Databricks data is not available."
        return DataSourceUnavailableError(f"{reason} Retrying in about {retry_after} s.", retry_after=retry_after)

    # --- loading ------------------------------------------------------------------------------

    def _load(self) -> RetailDataset:
        """Read, convert, and validate all five tables. Raises DataSourceUnavailableError."""
        started = time.perf_counter()
        try:
            names = {spec.name: qualified_table(self.settings, spec.name) for spec in TABLE_SPECS}
        except InvalidIdentifierError as exc:
            raise DataSourceUnavailableError(
                "DATABRICKS_CATALOG and DATABRICKS_SCHEMA must be simple identifiers (letters, digits, underscore)."
            ) from exc

        tables: dict[str, list[dict[str, Any]]] = {}
        try:
            with self._connect(self.settings) as connection, connection.cursor(
                arraysize=FETCH_BATCH_ROWS, row_limit=MAX_ROWS_PER_TABLE + 1
            ) as cursor:
                for spec in TABLE_SPECS:
                    cursor.execute(f"SELECT {', '.join(spec.column_names)} FROM {names[spec.name]}")
                    validate_description(spec, cursor.description)
                    tables[spec.name] = self._fetch(cursor, spec)
        except ResultValidationError as exc:
            logger.error("Databricks %s validation failed: %s", exc.kind, sanitize_error(exc, self.settings))
            raise DataSourceUnavailableError(f"Databricks table {exc.kind} did not match the expected definition.") from exc
        except Exception as exc:
            category = classify_error(exc)
            logger.error("Databricks read failed [%s]: %s", category, sanitize_error(exc, self.settings))
            raise DataSourceUnavailableError(ERROR_MESSAGES[category]) from exc

        try:
            validate_relations(tables)
        except ResultValidationError as exc:
            logger.error("Databricks data validation failed: %s", sanitize_error(exc, self.settings))
            raise DataSourceUnavailableError("Databricks data did not match the expected definition.") from exc

        logger.info(
            "Loaded Databricks tables in %.1fs (%s)",
            time.perf_counter() - started,
            ", ".join(f"{name}={len(rows)}" for name, rows in tables.items()),
        )
        return _build(self.source, tables)

    @staticmethod
    def _fetch(cursor: Any, spec) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        while True:
            batch = cursor.fetchmany(FETCH_BATCH_ROWS)
            if not batch:
                break
            rows.extend(convert_rows(spec, batch, errors))
            if len(rows) + len(errors) > MAX_ROWS_PER_TABLE:
                raise ResultValidationError("data", [f"{spec.name}: more than {MAX_ROWS_PER_TABLE:,} rows"])
            if len(errors) > 20:
                break
        if errors:
            raise ResultValidationError("data", errors)
        return rows


# --- FastAPI dependencies ----------------------------------------------------------------------


@lru_cache
def _repository(source: str, data_dir: str, refresh_seconds: float, wait_seconds: float) -> Repository:
    if source == "databricks":
        logger.warning("Using the UNVERIFIED Databricks data source")
        return DatabricksRepository(get_databricks_settings(), refresh_seconds=refresh_seconds, wait_seconds=wait_seconds)
    return CsvRepository(Path(data_dir))


def get_repository(settings: Settings = Depends(get_settings)) -> Repository:
    """FastAPI dependency: one repository per configured source (kept across requests)."""
    return _repository(settings.data_source, str(settings.data_dir), settings.data_refresh_seconds, settings.data_wait_seconds)


def freshness_headers(freshness: Freshness) -> dict[str, str]:
    headers = {"X-Data-Source": freshness.source, "X-Data-Stale": str(freshness.stale).lower()}
    if freshness.loaded_at:
        headers["X-Data-Loaded-At"] = freshness.loaded_at.isoformat(timespec="seconds")
    if freshness.age_seconds is not None:
        headers["X-Data-Age-Seconds"] = str(int(freshness.age_seconds))
    if freshness.last_error:
        headers["X-Data-Refresh-Failed"] = "true"
    return headers


def get_dataset(response: Response, repository: Repository = Depends(get_repository)) -> RetailDataset:
    """FastAPI dependency: the current dataset plus X-Data-* freshness headers.

    Raises DataSourceUnavailableError (HTTP 503, with Retry-After when known).
    """
    dataset = repository.dataset()
    response.headers.update(freshness_headers(repository.freshness()))
    return dataset


def clear_repository_cache() -> None:
    _repository.cache_clear()
