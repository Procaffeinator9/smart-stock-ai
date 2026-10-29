// Shapes of GET /api/v1/purchase-orders/summary and /api/v1/purchase-orders
// (backend/app/api/v1/purchase_order_schemas.py and schemas.py; definitions in
// backend/app/analytics/purchase_orders.py).
import type { DataFreshness, PurchaseOrderStatus } from "@/lib/dashboard/types";
import type { SupplierFacet } from "@/lib/sales/types";

export interface PurchaseOrder {
  purchase_order_id: string;
  supplier_id: string;
  supplier_name: string;
  product_id: string;
  product_name: string;
  category: string;
  store_id: string;
  order_date: string;
  expected_delivery_date: string;
  actual_delivery_date: string | null;
  quantity_ordered: number;
  unit_cost: number;
  value: number;
  order_status: PurchaseOrderStatus;
  /** Delivered after the promised date, or open and past it. */
  is_late: boolean;
  is_overdue: boolean;
  days_overdue: number | null;
  days_late: number | null;
}

export interface PurchaseOrderPage {
  items: PurchaseOrder[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  source: "csv" | "databricks";
  as_of: string | null;
}

export interface OrderAmounts {
  orders: number;
  value: number;
  units: number;
}

export interface AgingBucket extends OrderAmounts {
  label: string;
  min_days: number;
  max_days: number | null;
}

export interface WeeklyOrders extends OrderAmounts {
  week_start: string;
  date_from: string;
  date_to: string;
  days: number;
  cancelled: number;
}

export interface WeeklyDelivery {
  week_start: string;
  date_from: string;
  date_to: string;
  days: number;
  on_time: number;
  late: number;
  overdue: number;
  on_time_rate: number | null;
}

export interface PurchaseOrderSummary {
  status: "ok";
  freshness: DataFreshness;
  source: "csv" | "databricks";
  /** Latest inventory snapshot date: lateness is judged as of this date (not today's date). */
  as_of: string;
  bounds: { date_from: string | null; date_to: string | null };
  period: { date_from: string | null; date_to: string | null };
  filters: { store_id: string | null; supplier_id: string | null; category: string | null; product_id: string | null };
  facets: { stores: string[]; categories: string[]; suppliers: SupplierFacet[] };
  totals: OrderAmounts;
  by_status: Array<OrderAmounts & { status: PurchaseOrderStatus }>;
  open: OrderAmounts;
  overdue: OrderAmounts & {
    avg_days_overdue: number | null;
    max_days_overdue: number | null;
    aging: AgingBucket[];
    top: PurchaseOrder[];
  };
  delivery: {
    delivered: number;
    on_time: number;
    late: number;
    overdue_open: number;
    on_time_rate: number | null;
    on_time_rate_definition: string;
    delivered_only_on_time_rate: number | null;
    delivered_only_definition: string;
    avg_days_late: number | null;
    max_days_late: number | null;
    avg_promised_lead_days: number | null;
    avg_actual_lead_days: number | null;
  };
  cancellation: { orders: number; cancelled: number; rate: number | null; definition: string };
  inbound: OrderAmounts & {
    date_from: string;
    date_to: string;
    days: Array<OrderAmounts & { date: string }>;
    later: OrderAmounts;
  };
  weekly_orders: WeeklyOrders[];
  weekly_delivery: WeeklyDelivery[];
}

export type PurchaseOrderSummaryResponse =
  | PurchaseOrderSummary
  | { status: "empty"; freshness: DataFreshness; source: "csv" | "databricks"; reason: string };
