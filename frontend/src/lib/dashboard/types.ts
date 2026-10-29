// Shape of src/data/overview-snapshot.json, produced by
// backend/scripts/export_dashboard_snapshot.py (backend/app/analytics/overview.py).

export type PositionStatus = "out_of_stock" | "critical" | "low" | "healthy";
export type PurchaseOrderStatus = "PLACED" | "IN_TRANSIT" | "DELIVERED" | "CANCELLED";

export type DataSourceName = "synthetic" | "csv" | "databricks";

export interface SnapshotMeta {
  schema_version: number;
  /** "synthetic" for the offline export; "csv" or "databricks" for the live API. */
  source: DataSourceName;
  generator: string | null;
  seed: number | null;
  start_date: string;
  end_date: string;
  as_of: string;
  stores: string[];
  categories: string[];
  currency: string;
}

export interface InventorySummary {
  inventory_value: number;
  inventory_units: number;
  low_stock_products: number;
  stockout_risk_products: number;
  positions: Record<PositionStatus, number>;
}

export interface DailySeries {
  dates: string[];
  revenue: number[];
  units: number[];
  category_revenue: Record<string, number[]>;
  inventory_value: number[];
  low_stock_products: number[];
  stockout_risk_products: number[];
}

export interface InventoryAlert {
  product_id: string;
  product_name: string;
  sku: string;
  category: string;
  supplier_name: string;
  store_id: string;
  status: PositionStatus;
  available: number;
  on_hand: number;
  reserved: number;
  reorder_point: number;
  safety_stock: number;
  avg_daily_units: number;
  days_of_cover: number | null;
  next_delivery: string | null;
}

export interface PurchaseOrderRow {
  purchase_order_id: string;
  supplier_name: string;
  product_name: string;
  store_id: string;
  quantity: number;
  value: number;
  order_date: string;
  expected_delivery_date: string;
  actual_delivery_date: string | null;
  status: PurchaseOrderStatus;
  is_late: boolean;
}

export interface PurchaseOrderSummary {
  open: number;
  overdue: number;
  delivered_last_30_days: number;
  on_time_rate_last_30_days: number | null;
}

export interface StoreHealth extends Record<PositionStatus, number> {
  store_id: string;
  positions: number;
  inventory_value: number;
}

export interface ForecastPoint {
  date: string;
  units: number;
  low: number;
  high: number;
}

export interface Forecast {
  method: string;
  history: Array<{ date: string; units: number }>;
  projection: ForecastPoint[];
}

export interface ProductIndexEntry {
  product_id: string;
  product_name: string;
  sku: string;
  category: string;
  supplier_name: string;
  selling_price: number;
  on_hand: number;
  available: number;
  status: PositionStatus;
  stores_at_risk: number;
}

export interface OverviewSnapshot {
  meta: SnapshotMeta;
  kpis: {
    total_products: number;
    categories: number;
    suppliers: number;
    stores: number;
    current: InventorySummary;
    week_before: InventorySummary | null;
  };
  daily: DailySeries;
  alerts: InventoryAlert[];
  purchase_orders: {
    summary: PurchaseOrderSummary;
    recent: PurchaseOrderRow[];
    overdue: PurchaseOrderRow[];
  };
  store_health: StoreHealth[];
  forecast: Forecast;
  products: ProductIndexEntry[];
}

/** What the overview page needs; the product search index is passed to the shell separately. */
export type OverviewData = Omit<OverviewSnapshot, "products">;

/** Freshness of the API's cached data snapshot (GET /api/v1/data-source; also in /overview). */
export interface DataFreshness {
  source: "csv" | "databricks";
  loaded_at: string | null;
  age_seconds: number | null;
  stale: boolean;
  refreshing: boolean;
  last_error: string | null;
  last_error_at: string | null;
  next_retry_in_seconds: number | null;
}

/** GET /api/v1/overview (backend/app/api/v1/overview_schemas.py). */
export type OverviewResponse =
  | (OverviewData & { status: "ok"; freshness: DataFreshness })
  | { status: "empty"; freshness: DataFreshness; source: "csv" | "databricks"; reason: string };
