// Mirrors the FastAPI response of GET /api/v1/inventory (backend/app/api/v1/schemas.py).
import type { PositionStatus } from "@/lib/dashboard/types";

export type OpenPurchaseOrderStatus = "PLACED" | "IN_TRANSIT" | "OPEN";

export interface OpenPurchaseOrder {
  purchase_order_id: string;
  supplier_id: string;
  quantity: number;
  order_date: string;
  expected_delivery_date: string;
  status: OpenPurchaseOrderStatus;
  is_overdue: boolean;
}

export interface InventoryPosition {
  snapshot_date: string;
  store_id: string;
  product_id: string;
  product_name: string;
  sku: string;
  category: string;
  supplier_id: string;
  supplier_name: string;
  status: PositionStatus;
  on_hand: number;
  reserved: number;
  available: number;
  reorder_point: number;
  safety_stock: number;
  avg_daily_units: number;
  days_of_cover: number | null;
  open_po_count: number;
  open_po_quantity: number;
  inventory_position: number;
  next_delivery: string | null;
  next_delivery_overdue: boolean;
  open_purchase_orders: OpenPurchaseOrder[];
}

export interface InventoryPage {
  items: InventoryPosition[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  source: "csv" | "databricks";
  as_of: string;
  summary: Record<PositionStatus, number>;
  facets: { stores: string[]; categories: string[] };
}
