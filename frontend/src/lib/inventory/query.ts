// The Inventory page keeps its filters, sort, and page in the URL so views are shareable and
// the back button works. These helpers convert between URL search params and a typed query.
import type { PositionStatus } from "@/lib/dashboard/types";

export const SORT_FIELDS = [
  "severity",
  "product_name",
  "store_id",
  "category",
  "available",
  "days_of_cover",
  "reorder_point",
  "safety_stock",
  "inventory_position",
  "next_delivery",
] as const;
export type SortField = (typeof SORT_FIELDS)[number];
export type SortOrder = "asc" | "desc";

export const STATUSES: PositionStatus[] = ["out_of_stock", "critical", "low", "healthy"];
export const PAGE_SIZES = [10, 25, 50, 100] as const;
const DEFAULT_PAGE_SIZE = 25;

export interface InventoryQuery {
  search: string;
  store: string | null;
  category: string | null;
  status: PositionStatus[];
  sort: SortField;
  order: SortOrder;
  page: number;
  pageSize: number;
}

export const DEFAULT_QUERY: InventoryQuery = {
  search: "",
  store: null,
  category: null,
  status: [],
  sort: "severity",
  order: "asc",
  page: 1,
  pageSize: DEFAULT_PAGE_SIZE,
};

type RawParams = Record<string, string | string[] | undefined>;

const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);
const all = (value: string | string[] | undefined) => (value === undefined ? [] : Array.isArray(value) ? value : [value]);

/** Unknown or malformed values fall back to defaults instead of erroring. */
export function parseQuery(params: RawParams): InventoryQuery {
  const sort = first(params.sort);
  const page = Number.parseInt(first(params.page) ?? "", 10);
  const pageSize = Number.parseInt(first(params.page_size) ?? "", 10);
  return {
    search: (first(params.search) ?? "").slice(0, 100),
    store: first(params.store_id) || null,
    category: first(params.category) || null,
    status: all(params.status).filter((s): s is PositionStatus => STATUSES.includes(s as PositionStatus)),
    sort: SORT_FIELDS.includes(sort as SortField) ? (sort as SortField) : DEFAULT_QUERY.sort,
    order: first(params.order) === "desc" ? "desc" : "asc",
    page: Number.isFinite(page) && page > 0 ? page : 1,
    pageSize: (PAGE_SIZES as readonly number[]).includes(pageSize) ? pageSize : DEFAULT_PAGE_SIZE,
  };
}

/** Query string for the page URL (defaults omitted). */
export function toSearchParams(query: InventoryQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.search.trim()) params.set("search", query.search.trim());
  if (query.store) params.set("store_id", query.store);
  if (query.category) params.set("category", query.category);
  for (const status of query.status) params.append("status", status);
  if (query.sort !== DEFAULT_QUERY.sort) params.set("sort", query.sort);
  if (query.order !== DEFAULT_QUERY.order) params.set("order", query.order);
  if (query.page !== 1) params.set("page", String(query.page));
  if (query.pageSize !== DEFAULT_PAGE_SIZE) params.set("page_size", String(query.pageSize));
  return params;
}

/** Query string for GET /api/v1/inventory (same names; page_size always sent). */
export function toApiParams(query: InventoryQuery): URLSearchParams {
  const params = toSearchParams(query);
  params.set("page", String(query.page));
  params.set("page_size", String(query.pageSize));
  return params;
}

export function hasActiveFilters(query: InventoryQuery): boolean {
  return Boolean(query.search.trim() || query.store || query.category || query.status.length);
}
