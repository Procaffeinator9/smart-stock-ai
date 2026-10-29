// The Suppliers scorecard keeps its search, attention filter and sort in the URL, so views are
// shareable and the back button works. URL parameters use the API's names. No runtime imports, so
// the tests in frontend/tests can load this file directly with Node's built-in test runner.

export const SCORE_SORT_FIELDS = [
  "attention",
  "supplier_name",
  "on_time_rate",
  "reliability_gap",
  "stated_reliability",
  "lead_time_gap_days",
  "spend",
  "orders",
  "overdue_orders",
  "at_risk_positions",
  "revenue",
  "stockout_days",
] as const;
export type ScoreSortField = (typeof SCORE_SORT_FIELDS)[number];
export type SortOrder = "asc" | "desc";

/** "flagged": only suppliers with a Needs attention flag; "clear": only those without. */
export type AttentionFilter = "all" | "flagged" | "clear";

const MAX_SEARCH_LENGTH = 100;

export interface SupplierQuery {
  search: string;
  attention: AttentionFilter;
  sort: ScoreSortField;
  order: SortOrder;
}

export const DEFAULT_SUPPLIER_QUERY: SupplierQuery = { search: "", attention: "all", sort: "attention", order: "desc" };

// Worst first by default: lowest rates and gaps, otherwise the largest values. Names A–Z.
const ASCENDING_FIRST = new Set<ScoreSortField>(["supplier_name", "on_time_rate", "reliability_gap", "stated_reliability"]);

type RawParams = Record<string, string | string[] | undefined>;

const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);

/** Unknown or malformed values fall back to defaults instead of erroring. */
export function parseSupplierQuery(params: RawParams): SupplierQuery {
  const sort = first(params.sort);
  const order = first(params.order);
  const attention = first(params.attention);
  return {
    search: (first(params.search) ?? "").slice(0, MAX_SEARCH_LENGTH),
    attention: attention === "true" ? "flagged" : attention === "false" ? "clear" : "all",
    sort: SCORE_SORT_FIELDS.includes(sort as ScoreSortField) ? (sort as ScoreSortField) : DEFAULT_SUPPLIER_QUERY.sort,
    order: order === "asc" || order === "desc" ? order : DEFAULT_SUPPLIER_QUERY.order,
  };
}

/** Query string for the page URL and for GET /api/v1/suppliers/performance (defaults omitted). */
export function toSearchParams(query: SupplierQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.search.trim()) params.set("search", query.search.trim());
  if (query.attention !== "all") params.set("attention", query.attention === "flagged" ? "true" : "false");
  if (query.sort !== DEFAULT_SUPPLIER_QUERY.sort) params.set("sort", query.sort);
  if (query.order !== DEFAULT_SUPPLIER_QUERY.order) params.set("order", query.order);
  return params;
}

export function hasActiveFilters(query: SupplierQuery): boolean {
  return Boolean(query.search.trim() || query.attention !== "all");
}

export function nextSort(query: SupplierQuery, field: ScoreSortField): Pick<SupplierQuery, "sort" | "order"> {
  if (query.sort === field) return { sort: field, order: query.order === "asc" ? "desc" : "asc" };
  return { sort: field, order: ASCENDING_FIRST.has(field) ? "asc" : "desc" };
}

/** Links from a supplier to the other pages, already filtered to that supplier. */
export function supplierLinks(supplierId: string, supplierName: string) {
  const id = encodeURIComponent(supplierId);
  return {
    detail: `/suppliers/${id}`,
    orders: `/purchase-orders?supplier_id=${id}`,
    overdueOrders: `/purchase-orders?supplier_id=${id}&overdue=true&sort=days_overdue`,
    sales: `/sales?supplier_id=${id}`,
    // Inventory search matches supplier names.
    stock: `/inventory?search=${encodeURIComponent(supplierName)}`,
    atRiskStock: `/inventory?search=${encodeURIComponent(supplierName)}&status=out_of_stock&status=critical`,
  };
}

/** Inventory positions of one product (Inventory search matches SKUs). */
export function productStockLink(sku: string): string {
  return `/inventory?search=${encodeURIComponent(sku)}`;
}
