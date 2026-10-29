// Shapes of GET /api/v1/sales/summary and /api/v1/sales/products
// (backend/app/api/v1/sales_schemas.py; definitions in backend/app/analytics/sales.py).
import type { DataFreshness } from "@/lib/dashboard/types";

export interface SalesPeriod {
  date_from: string;
  date_to: string;
  days: number;
}

export interface SalesKpiTotals {
  revenue: number;
  units: number;
  gross_margin: number;
  margin_rate: number | null;
  avg_unit_price: number | null;
  sale_lines: number;
  products_sold: number;
  promo_revenue: number;
  promo_units: number;
  promo_revenue_share: number | null;
  promo_units_share: number | null;
  stockout_days: number;
}

/** Aligned arrays: element i of every series belongs to dates[i]. */
export interface SalesDailySeries {
  dates: string[];
  revenue: number[];
  units: number[];
  gross_margin: number[];
  promo_revenue: number[];
}

interface Breakdown {
  revenue: number;
  units: number;
  gross_margin: number;
  margin_rate: number | null;
  share: number;
  previous_revenue: number | null;
  change: number | null;
}

export interface CategorySales extends Breakdown {
  category: string;
}

export interface StoreSales extends Breakdown {
  store_id: string;
}

export interface PromotionMetrics {
  promo_revenue: number;
  promo_units: number;
  promo_lines: number;
  revenue_share: number | null;
  units_share: number | null;
  avg_discount: number | null;
  promoted_products: number;
  units_per_line_promo: number | null;
  units_per_line_regular: number | null;
  uplift: number | null;
}

export interface SupplierFacet {
  supplier_id: string;
  supplier_name: string;
}

export interface SalesSummary {
  status: "ok";
  freshness: DataFreshness;
  source: "csv" | "databricks";
  /** Latest inventory snapshot date in the data (not today's date). */
  as_of: string | null;
  bounds: SalesPeriod;
  period: SalesPeriod;
  previous_period: SalesPeriod | null;
  filters: { store_id: string | null; category: string | null; supplier_id: string | null; promotion: boolean | null };
  facets: { stores: string[]; categories: string[]; suppliers: SupplierFacet[] };
  kpis: { current: SalesKpiTotals; previous: SalesKpiTotals | null };
  daily: SalesDailySeries;
  by_category: CategorySales[];
  by_store: StoreSales[];
  promotion: PromotionMetrics;
}

export type SalesSummaryResponse =
  | SalesSummary
  | { status: "empty"; freshness: DataFreshness; source: "csv" | "databricks"; reason: string };

export interface ProductPerformance {
  product_id: string;
  product_name: string;
  sku: string;
  category: string;
  supplier_id: string;
  supplier_name: string;
  revenue: number;
  units: number;
  gross_margin: number;
  margin_rate: number | null;
  avg_unit_price: number | null;
  revenue_share: number | null;
  promo_revenue_share: number | null;
  stores_sold: number;
  stockout_days: number;
  previous_revenue: number | null;
  revenue_change: number | null;
}

export interface ProductPerformancePage {
  items: ProductPerformance[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  source: "csv" | "databricks";
  period: SalesPeriod | null;
  previous_period: SalesPeriod | null;
}
