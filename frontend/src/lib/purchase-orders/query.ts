// The Purchase Orders page keeps its filters, sort, and page in the URL, so views are shareable
// and the back button works. URL parameters use the API's names. No runtime imports, so the tests
// in frontend/tests can load this file directly with Node's built-in test runner.
import type { PurchaseOrderStatus } from "@/lib/dashboard/types";

export const PO_STATUSES: PurchaseOrderStatus[] = ["PLACED", "IN_TRANSIT", "DELIVERED", "CANCELLED"];
export const RANGE_PRESETS = [7, 30, 90] as const;
export type RangePreset = (typeof RANGE_PRESETS)[number];

export const ORDER_SORT_FIELDS = [
  "order_date",
  "expected_delivery_date",
  "actual_delivery_date",
  "quantity_ordered",
  "value",
  "days_overdue",
  "days_late",
  "purchase_order_id",
] as const;
export type OrderSortField = (typeof ORDER_SORT_FIELDS)[number];
export type SortOrder = "asc" | "desc";

/** Narrow the table to overdue open orders or to orders delivered late (they never overlap). */
export type LatenessFilter = "all" | "overdue" | "late";

export const PAGE_SIZES = [10, 25, 50, 100] as const;
const DEFAULT_PAGE_SIZE = 25;
const MAX_SEARCH_LENGTH = 100;

export interface PurchaseOrderQuery {
  /** Orders placed in the last N days up to the as-of date; null = every order date (unless from/to is set). */
  days: RangePreset | null;
  from: string | null;
  to: string | null;
  store: string | null;
  supplier: string | null;
  category: string | null;
  /** Not shown as a control (search covers products); kept so links can scope to one product. */
  product: string | null;
  status: PurchaseOrderStatus[];
  lateness: LatenessFilter;
  search: string;
  sort: OrderSortField;
  order: SortOrder;
  page: number;
  pageSize: number;
}

export const DEFAULT_PO_QUERY: PurchaseOrderQuery = {
  days: null,
  from: null,
  to: null,
  store: null,
  supplier: null,
  category: null,
  product: null,
  status: [],
  lateness: "all",
  search: "",
  sort: "order_date",
  order: "desc",
  page: 1,
  pageSize: DEFAULT_PAGE_SIZE,
};

type RawParams = Record<string, string | string[] | undefined>;

const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);
const all = (value: string | string[] | undefined) => (value === undefined ? [] : Array.isArray(value) ? value : [value]);

/** A real calendar date in YYYY-MM-DD form, or null. */
export function isoDateOrNull(value: string | undefined): string | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value ? value : null;
}

export function isCustomRange(query: PurchaseOrderQuery): boolean {
  return query.from !== null || query.to !== null;
}

/** Unknown or malformed values fall back to defaults instead of erroring. */
export function parsePurchaseOrderQuery(params: RawParams): PurchaseOrderQuery {
  const days = Number.parseInt(first(params.days) ?? "", 10);
  const sort = first(params.sort);
  const order = first(params.order);
  const page = Number.parseInt(first(params.page) ?? "", 10);
  const pageSize = Number.parseInt(first(params.page_size) ?? "", 10);
  const from = isoDateOrNull(first(params.date_from));
  const to = isoDateOrNull(first(params.date_to));
  const statuses = all(params.status);
  return {
    days: from || to || !(RANGE_PRESETS as readonly number[]).includes(days) ? null : (days as RangePreset),
    from,
    to,
    store: first(params.store_id) || null,
    supplier: first(params.supplier_id) || null,
    category: first(params.category) || null,
    product: first(params.product_id) || null,
    status: PO_STATUSES.filter((s) => statuses.includes(s)),
    lateness: first(params.overdue) === "true" ? "overdue" : first(params.delivered_late) === "true" ? "late" : "all",
    search: (first(params.search) ?? "").slice(0, MAX_SEARCH_LENGTH),
    sort: ORDER_SORT_FIELDS.includes(sort as OrderSortField) ? (sort as OrderSortField) : DEFAULT_PO_QUERY.sort,
    order: order === "asc" || order === "desc" ? order : DEFAULT_PO_QUERY.order,
    page: Number.isFinite(page) && page > 0 ? page : 1,
    pageSize: (PAGE_SIZES as readonly number[]).includes(pageSize) ? pageSize : DEFAULT_PAGE_SIZE,
  };
}

/** Scope filters shared by the summary and the list (order-date window, store, supplier, category, product). */
export function toSummaryParams(query: PurchaseOrderQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (isCustomRange(query)) {
    if (query.from) params.set("date_from", query.from);
    if (query.to) params.set("date_to", query.to);
  } else if (query.days !== null) {
    params.set("days", String(query.days));
  }
  if (query.store) params.set("store_id", query.store);
  if (query.supplier) params.set("supplier_id", query.supplier);
  if (query.category) params.set("category", query.category);
  if (query.product) params.set("product_id", query.product);
  return params;
}

/** Query string for the page URL (defaults omitted). */
export function toSearchParams(query: PurchaseOrderQuery): URLSearchParams {
  const params = toSummaryParams(query);
  for (const status of query.status) params.append("status", status);
  if (query.lateness === "overdue") params.set("overdue", "true");
  if (query.lateness === "late") params.set("delivered_late", "true");
  if (query.search.trim()) params.set("search", query.search.trim());
  if (query.sort !== DEFAULT_PO_QUERY.sort) params.set("sort", query.sort);
  if (query.order !== DEFAULT_PO_QUERY.order) params.set("order", query.order);
  if (query.page !== 1) params.set("page", String(query.page));
  if (query.pageSize !== DEFAULT_PAGE_SIZE) params.set("page_size", String(query.pageSize));
  return params;
}

/** Query string for GET /api/v1/purchase-orders (page and page_size always sent). */
export function toListParams(query: PurchaseOrderQuery): URLSearchParams {
  const params = toSearchParams(query);
  params.set("page", String(query.page));
  params.set("page_size", String(query.pageSize));
  return params;
}

/** Filters that narrow the data (the order-date window is shown separately). */
export function hasActiveFilters(query: PurchaseOrderQuery): boolean {
  return Boolean(
    query.store || query.supplier || query.category || query.product || query.status.length || query.lateness !== "all" || query.search.trim(),
  );
}

/** Sorting a column: start with the most useful direction (dates and amounts high to low), then toggle. */
export function nextSort(query: PurchaseOrderQuery, field: OrderSortField): Pick<PurchaseOrderQuery, "sort" | "order"> {
  if (query.sort === field) return { sort: field, order: query.order === "asc" ? "desc" : "asc" };
  return { sort: field, order: field === "purchase_order_id" ? "asc" : "desc" };
}

/** The view showing every overdue order, most overdue first. */
export function overdueView(query: PurchaseOrderQuery): PurchaseOrderQuery {
  return { ...query, status: [], lateness: "overdue", search: "", sort: "days_overdue", order: "desc", page: 1 };
}
