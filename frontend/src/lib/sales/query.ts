// The Sales page keeps its filters, product-table sort and page in the URL, so views are
// shareable and the back button works. URL parameters use the API's names. No runtime imports,
// so the tests in frontend/tests can load this file directly with Node's built-in test runner.

export const RANGE_PRESETS = [7, 30, 90] as const;
export type RangePreset = (typeof RANGE_PRESETS)[number];

export const PRODUCT_SORT_FIELDS = [
  "revenue",
  "units",
  "gross_margin",
  "margin_rate",
  "avg_unit_price",
  "promo_revenue_share",
  "stockout_days",
  "revenue_change",
  "product_name",
  "category",
] as const;
export type ProductSortField = (typeof PRODUCT_SORT_FIELDS)[number];
export type SortOrder = "asc" | "desc";

export type PromotionFilter = "all" | "promo" | "regular";

export const PAGE_SIZES = [10, 25, 50, 100] as const;
const DEFAULT_PAGE_SIZE = 25;
const MAX_SEARCH_LENGTH = 100;

export interface SalesQuery {
  /** Window ending at the last sale date; ignored when a custom range (from/to) is set. */
  days: RangePreset;
  from: string | null;
  to: string | null;
  store: string | null;
  category: string | null;
  supplier: string | null;
  promotion: PromotionFilter;
  search: string;
  sort: ProductSortField;
  order: SortOrder;
  page: number;
  pageSize: number;
}

export const DEFAULT_SALES_QUERY: SalesQuery = {
  days: 30,
  from: null,
  to: null,
  store: null,
  category: null,
  supplier: null,
  promotion: "all",
  search: "",
  sort: "revenue",
  order: "desc",
  page: 1,
  pageSize: DEFAULT_PAGE_SIZE,
};

type RawParams = Record<string, string | string[] | undefined>;

const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);

/** A real calendar date in YYYY-MM-DD form, or null. */
export function isoDateOrNull(value: string | undefined): string | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value ? value : null;
}

export function isCustomRange(query: SalesQuery): boolean {
  return query.from !== null || query.to !== null;
}

/** Unknown or malformed values fall back to defaults instead of erroring. */
export function parseSalesQuery(params: RawParams): SalesQuery {
  const days = Number.parseInt(first(params.days) ?? "", 10);
  const sort = first(params.sort);
  const promotion = first(params.promotion);
  const page = Number.parseInt(first(params.page) ?? "", 10);
  const pageSize = Number.parseInt(first(params.page_size) ?? "", 10);
  return {
    days: (RANGE_PRESETS as readonly number[]).includes(days) ? (days as RangePreset) : DEFAULT_SALES_QUERY.days,
    from: isoDateOrNull(first(params.date_from)),
    to: isoDateOrNull(first(params.date_to)),
    store: first(params.store_id) || null,
    category: first(params.category) || null,
    supplier: first(params.supplier_id) || null,
    promotion: promotion === "true" ? "promo" : promotion === "false" ? "regular" : "all",
    search: (first(params.search) ?? "").slice(0, MAX_SEARCH_LENGTH),
    sort: PRODUCT_SORT_FIELDS.includes(sort as ProductSortField) ? (sort as ProductSortField) : DEFAULT_SALES_QUERY.sort,
    order: first(params.order) === "asc" ? "asc" : first(params.order) === "desc" ? "desc" : DEFAULT_SALES_QUERY.order,
    page: Number.isFinite(page) && page > 0 ? page : 1,
    pageSize: (PAGE_SIZES as readonly number[]).includes(pageSize) ? pageSize : DEFAULT_PAGE_SIZE,
  };
}

/** Window and filters, as the API expects them (shared by both endpoints). */
export function toSummaryParams(query: SalesQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (isCustomRange(query)) {
    if (query.from) params.set("date_from", query.from);
    if (query.to) params.set("date_to", query.to);
  } else if (query.days !== DEFAULT_SALES_QUERY.days) {
    params.set("days", String(query.days));
  }
  if (query.store) params.set("store_id", query.store);
  if (query.category) params.set("category", query.category);
  if (query.supplier) params.set("supplier_id", query.supplier);
  if (query.promotion !== "all") params.set("promotion", query.promotion === "promo" ? "true" : "false");
  return params;
}

/** Query string for the page URL (defaults omitted). */
export function toSearchParams(query: SalesQuery): URLSearchParams {
  const params = toSummaryParams(query);
  if (query.search.trim()) params.set("search", query.search.trim());
  if (query.sort !== DEFAULT_SALES_QUERY.sort) params.set("sort", query.sort);
  if (query.order !== DEFAULT_SALES_QUERY.order) params.set("order", query.order);
  if (query.page !== 1) params.set("page", String(query.page));
  if (query.pageSize !== DEFAULT_PAGE_SIZE) params.set("page_size", String(query.pageSize));
  return params;
}

/** Query string for GET /api/v1/sales/products (page and page_size always sent). */
export function toProductParams(query: SalesQuery): URLSearchParams {
  const params = toSearchParams(query);
  params.set("page", String(query.page));
  params.set("page_size", String(query.pageSize));
  return params;
}

/** Filters that narrow the data (the date window is not a filter: there is always one). */
export function hasActiveFilters(query: SalesQuery): boolean {
  return Boolean(query.store || query.category || query.supplier || query.promotion !== "all" || query.search.trim());
}

/** Sorting a column: start with the most useful direction, then toggle. */
export function nextSort(query: SalesQuery, field: ProductSortField): Pick<SalesQuery, "sort" | "order"> {
  if (query.sort === field) return { sort: field, order: query.order === "asc" ? "desc" : "asc" };
  return { sort: field, order: field === "product_name" || field === "category" ? "asc" : "desc" };
}
