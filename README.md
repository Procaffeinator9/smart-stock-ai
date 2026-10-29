# SmartStock AI

A personal portfolio project covering full stack development, data engineering, and AI:
retail inventory intelligence (demand forecasting and replenishment) built on a Next.js
frontend, a FastAPI backend, and Delta tables in Databricks.

> All data in this project is **synthetic**, produced by a deterministic generator. No real
> company, customer, or employer data is used.

## Repository layout

```
smartstock-ai/
├─ frontend/                 Next.js 16 (App Router, TypeScript, Tailwind CSS v4)
│  └─ src/
│     ├─ app/                layout (app shell), Overview page, loading / error / not-found
│     ├─ components/shell/   sidebar, top bar, search palette, profile menu, API status
│     ├─ components/dashboard/  overview widgets (KPIs, charts, alerts, POs, forecast)
│     ├─ components/ui/      card, badges, dialog, segmented control, count-up, sparkline
│     ├─ data/               overview-snapshot.json (metrics calculated from synthetic data)
│     └─ lib/                api.ts (server-side backend client), dashboard data + formatting
├─ backend/                  FastAPI (Python 3.14)
│  ├─ app/
│  │  ├─ main.py             app factory, CORS
│  │  ├─ core/config.py      settings from environment variables
│  │  ├─ api/v1/             versioned routes (GET /api/v1/health)
│  │  ├─ db/databricks.py    Databricks SQL connection factory (env-configured, lazy)
│  │  ├─ analytics/          overview dashboard metrics
│  │  └─ synthetic/          deterministic retail data generator and CSV loader
│  ├─ scripts/               generate_synthetic_data.py, check_databricks_connection.py,
│  │                         load_synthetic_data.py, export_dashboard_snapshot.py
│  └─ tests/                 pytest suite
└─ databricks/
   ├─ README.md              table purposes, relationships, run order
   └─ sql/                   Delta DDL for workspace.smartstock_retail (run manually)
```

## Prerequisites (Windows)

- Node.js 20.9+ (developed on v24)
- Python 3.12+ (developed on 3.14) with the `py` launcher
- Git

All commands below are for **PowerShell**, starting from the repository root.

## Backend setup

```powershell
cd backend
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

If activation is blocked ("running scripts is disabled"), run this once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### Run the API

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

- Health: <http://localhost:8000/api/v1/health>
- Interactive docs: <http://localhost:8000/docs>

The health endpoint needs no Databricks credentials. `databricks_configured` only reports
whether the `DATABRICKS_*` variables are set. It does **not** test the connection.

### Run the tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest
```

Tests never contact Databricks, and they ignore any real `backend/.env`.

### Read-only data API (Phase 3)

All endpoints are `GET` only and live under `/api/v1`. Browse them at <http://localhost:8000/docs>.

| Endpoint | Filters | Sort fields |
|---|---|---|
| `/inventory` | `search`, `store_id`, `category`, `status` (repeatable), `has_open_po`, `snapshot_date` | `severity` (default), `product_name`, `store_id`, `category`, `available`, `days_of_cover`, `reorder_point`, `safety_stock`, `inventory_position`, `next_delivery` |
| `/products`, `/products/{id}` | `search`, `category`, `supplier_id` | `product_id`, `product_name`, `category`, `unit_cost`, `selling_price`, `created_at` |
| `/suppliers`, `/suppliers/{id}` | `search` | `supplier_id`, `supplier_name`, `lead_time_days`, `minimum_order_quantity`, `reliability_score` |
| `/sales` | `date_from`, `date_to`, `store_id`, `product_id`, `category`, `promotion` | `sale_date` (default, newest first), `quantity_sold`, `unit_selling_price`, `revenue`, `sale_id` |
| `/purchase-orders` | `search`, `status` (repeatable), `store_id`, `supplier_id`, `product_id`, `overdue`, `date_from`, `date_to` | `order_date` (default, newest first), `expected_delivery_date`, `quantity_ordered`, `value`, `purchase_order_id` |

- **Paging:** every list endpoint takes `page` (from 1) and `page_size` (1–100, default 25), plus
  `sort` and `order` (`asc` or `desc`). It returns `items`, `page`, `page_size`, `total`, and
  `total_pages`. A page past the end returns no items.
- **Responses:**
  - `/inventory` also returns `as_of`, `source`, status counts (`summary`), and the available
    stores and categories (`facets`).
  - `/sales` also returns `totals` across every matching row.
- **Errors:** invalid parameters return **422**, unknown IDs return **404**, and an unavailable
  data source returns **503** with a message.
- **Stock rules:** `backend/app/analytics/stock.py` holds the rules for stock status, days of
  cover, open orders, and lateness. The Overview dashboard uses the same rules.

**Data source** (set it in `backend/.env`):

| Setting | Default | Meaning |
|---|---|---|
| `SMARTSTOCK_DATA_SOURCE` | `csv` | `csv` reads the generated synthetic files. `databricks` runs read-only `SELECT`s on `workspace.smartstock_retail`. **The Databricks option is unverified:** it has only been tested against a fake connection. |
| `SMARTSTOCK_DATA_DIR` | `backend/data/synthetic` | Folder containing the five CSV files. |

- **CSV mode** checks the files the same way the Databricks loader does, keeps them in memory,
  reloads them when they change, and preloads them in the background when the API starts.
- **If the CSVs are missing**, the data endpoints return 503 telling you to run
  `python scripts/generate_synthetic_data.py`. `/health` keeps working and reports
  `data_source`.

**Databricks source safeguards** (Phase 4A; still **unverified** against a real warehouse):

- **Bounded connections.** Every connection from the API, `check_databricks_connection.py`,
  and the loader uses:
  - a 30 s socket timeout;
  - at most 3 attempts within a 60 s retry budget;
  - a 60 s server-side `STATEMENT_TIMEOUT`;
  - session time zone `UTC`;
  - connector telemetry turned off.

  The connector's own defaults are 900 s. Override them with the `DATABRICKS_*_SECONDS` and
  `DATABRICKS_RETRY_MAX_ATTEMPTS` settings (see `backend/.env.example`; out-of-range values are
  rejected).
- **Cached snapshot.** One background refresh runs at a time, every
  `SMARTSTOCK_DATA_REFRESH_SECONDS` (default 300). No lock is held during network I/O. If a
  refresh fails, the last validated snapshot keeps being served and retries back off from 15 s
  up to 5 minutes.
- **First load.** Before any snapshot exists, a request waits at most
  `SMARTSTOCK_DATA_WAIT_SECONDS` (default 10), then gets **503** with `Retry-After`.
- **Freshness metadata.** Data responses carry `X-Data-Source`, `X-Data-Loaded-At`,
  `X-Data-Age-Seconds`, `X-Data-Stale`, and (after a failed refresh) `X-Data-Refresh-Failed`.
  `GET /api/v1/data-source` reports the same state without triggering a load.
- **Validation.** Results are checked like the CSV path:
  - column names, order, types, and DECIMAL precision and scale;
  - strict type conversion (DATE, TIMESTAMP, and DECIMAL may arrive as text without pyarrow;
    timezone-aware timestamps are converted to UTC; NULL only in nullable columns);
  - CHECK constraints, keys, and foreign keys.

  Each table is capped at 1,000,000 rows and read in 50,000-row batches.
- **Arrow results.** `pyarrow` 25.0.1 is installed, so the connector requests Arrow results.
  - **Why:** without it, a full row-based refresh took 113 s (Phase 4B).
  - **How values are converted:** with Arrow's `.as_py()` (`_disable_pandas`), so they arrive as
    plain Python types. The same strict validation still applies.
  - **CloudFetch:** off by default, set with `DATABRICKS_USE_CLOUD_FETCH`. When on, large results
    are downloaded from cloud-storage links, which means a second host and a separate 60 s timeout.
  - **Fallback:** uninstalling `pyarrow` returns the connector to the row-based path; the code
    handles both.
  - **Checking which path is in use:** `validate_databricks_read.py` records the result format,
    the pyarrow version, and the CloudFetch setting in its report.
- **Configured names.** Tables are read from the configured `DATABRICKS_CATALOG` and
  `DATABRICKS_SCHEMA`, which must be simple identifiers and are backtick-quoted. The loader
  refuses to run unless they are `workspace.smartstock_retail`, the schema the DDL creates.
- **Sanitized errors.**
  - Logs and script output never include the token, hostname, HTTP path, or URLs; a log filter
    also covers the connector's own messages.
  - API errors are fixed category messages: timeout, credentials, not found, unreachable, or
    query failed.

## Frontend setup

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local   # optional; defaults to http://localhost:8000
npm run dev
```

Open <http://localhost:3000>. If port 3000 is taken, use `npm run dev -- -p 3100`.

Other commands: `npm run lint`, `npm run build`, `npm start`.

The frontend calls the backend **from the Next.js server** (`API_BASE_URL` has no
`NEXT_PUBLIC_` prefix), so the backend URL and any credentials never reach the browser.

### Overview dashboard (Phase 2)

The Overview page reads `frontend/src/data/overview-snapshot.json`. Every figure in it is
**calculated from the synthetic dataset** by `backend/app/analytics/overview.py`; nothing is
typed in by hand, and the page labels it as synthetic demo data. It does not use Databricks.
To regenerate it after changing the generator or the metric definitions:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts/export_dashboard_snapshot.py
```

`pytest` fails if the committed snapshot no longer matches what the exporter produces.

- **Built:** app shell (collapsible sidebar, mobile drawer, top bar), search palette
  (`Ctrl/⌘ K`, products and pages), 7/30/90-day date range, profile menu, "About this data"
  dialog, and the Overview widgets.
- **Not built yet:** Replenishment, Sales & Forecasting, Purchase Orders, Suppliers, and AI
  Copilot appear in the sidebar marked **Soon** and are not links. Dark theme and account
  settings are also marked Soon. There is no sign-in.

### Inventory page (Phase 3)

`/inventory` reads `GET /api/v1/inventory` from the Next.js server. It lists every store ×
product position on the latest snapshot date.

- **URL state:** search, store, category, status, sort, page, and page size all live in the URL,
  so a view can be shared and the back button works.
- **Search and filters:** search is debounced. Store and category are dropdowns, and the status
  chips are multi-select and show counts.
- **Sorting and paging:** click column headers to sort, or use the sort control on phones.
  Choose 10, 25, 50, or 100 rows per page.
- **Open purchase orders:** expand a row to see its open purchase orders and inventory position
  (available + on order). "Needs reorder" means the inventory position is at or below the
  reorder point.
- **States:** there are loading skeletons, a "no matches" state, an invalid-filter state, and
  states for an unreachable API or an unavailable data source. Phones get a card layout.
- **Links from elsewhere:** the Overview alerts card links to the at-risk view, and the search
  palette's product detail links to that product's stock by store.
- **Forecast preview** is a labelled baseline (same-weekday average of the last 4 weeks), not a
  trained model.
- **Motion** uses the `motion` library and follows the operating system's "reduce motion"
  setting: movement, count-ups, and chart animations are turned off.
- **Libraries:** `motion` (animation), `recharts` (charts, with keyboard/screen-reader support),
  `lucide-react` (icons), and `react-is` (a peer dependency of recharts). All are pinned to exact versions.

## Synthetic data

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts/generate_synthetic_data.py                       # defaults: seed 42
python scripts/generate_synthetic_data.py --seed 7 --products 50 --days 30
```

This writes `suppliers.csv`, `products.csv`, `sales.csv`, `inventory.csv`, and
`purchase_orders.csv` to `backend/data/synthetic/`, which is git-ignored. The same seed and
options always produce identical files. The defaults (20 suppliers, 200 products, 5 stores,
90 days from 2026-01-01) produce about 80k sales rows and exactly 90k inventory rows.

Sales, inventory, and purchase orders come from a day-by-day simulation: demand reduces
stock, and a purchase order is raised when stock (plus open orders) falls to the reorder
point. Deliveries arrive after the supplier's lead time, sometimes late depending on its
reliability score. CSV headers match the Delta column names exactly.

## Databricks

### 1. Create the tables (manual, one time)

See [databricks/README.md](databricks/README.md). Run `databricks/sql/00` to `07` in order in the
Databricks SQL editor. The scripts only create missing tables and never drop or overwrite.

### 2. Configure the backend connection

```powershell
cd backend
Copy-Item .env.example .env
notepad .env
```

Fill in the values from **SQL Warehouses → (your warehouse) → Connection details**:

| Variable | Example |
|---|---|
| `DATABRICKS_SERVER_HOSTNAME` | `dbc-xxxxxxxx-xxxx.cloud.databricks.com` |
| `DATABRICKS_HTTP_PATH` | `/sql/1.0/warehouses/xxxxxxxxxxxxxxxx` |
| `DATABRICKS_TOKEN` | personal access token (User settings → Developer → Access tokens) |
| `DATABRICKS_CATALOG` | `workspace` |
| `DATABRICKS_SCHEMA` | `smartstock_retail` |

`backend/.env` is git-ignored. The token is stored as a secret value and is never logged.

### 3. Check the connection (manual)

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts/check_databricks_connection.py
```

This runs one read-only probe query and lists the tables in the schema. It starts your SQL
Warehouse if it is stopped, which may incur cost.

> **Status:** the Databricks connection code has **not yet been tested** against a live
> workspace.

### 4. Load the synthetic CSVs (manual)

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts/generate_synthetic_data.py                 # if backend/data/synthetic is empty
python scripts/load_synthetic_data.py --validate-only     # local checks only, no connection
python scripts/load_synthetic_data.py                     # asks you to type 'load' before writing
```

The loader works in four phases:

1. **Validate CSVs locally.** It trims headers, converts every value to its column type, and
   checks NOT NULL, the CHECK constraints in `06_add_check_constraints.sql`, primary-key
   uniqueness, inventory `(snapshot_date, store_id, product_id)` uniqueness, and foreign keys.
   If anything fails, nothing is written.
2. **Check the target tables (read-only).** It confirms the five tables exist with the expected
   columns and types, then counts their rows. **It refuses to load if any table already has rows.**
3. **Insert in batches** in foreign-key order: suppliers, products, sales, inventory, then
   purchase_orders. The default is 500 rows per statement; change it with `--batch-size`.
4. **Re-count every table** and compare with the expected totals.

**The load is not atomic.** Each batch commits on its own, so if a run fails part-way, the rows
written so far stay in the tables. To finish the load, fix the cause and re-run with
`--allow-nonempty`. That mode uses an insert-only `MERGE` keyed on the primary key (plus the
inventory snapshot key), so rows that already exist are skipped, never duplicated or updated.

Exit codes: `0` success, `1` load failure, count mismatch, or aborted, `2` not configured,
`3` validation failed, `4` target tables not empty.

## Security notes

- Credentials come only from environment variables or `backend/.env`. Neither is committed.
- `.env.example` files contain placeholders only.
- The frontend never receives Databricks credentials.
- No script creates cloud resources or runs SQL automatically.
