// The Replenishment page keeps its filters, sort and page in the URL, so views are shareable and
// the back button works. No runtime imports, so the tests in frontend/tests can load this file
// directly with Node's built-in test runner.
import type { Action, Priority } from "./types";

export const PRIORITIES: Priority[] = ["critical", "high", "medium", "low"];

/** "needs_action" (the default) = Order now + Expedite; Watch rows are hidden unless asked for. */
export const VIEWS = ["needs_action", "order", "expedite", "watch", "all"] as const;
export type View = (typeof VIEWS)[number];

export const VIEW_ACTIONS: Record<View, Action[]> = {
  needs_action: ["order", "expedite"],
  order: ["order"],
  expedite: ["expedite"],
  watch: ["watch"],
  all: ["order", "expedite", "watch"],
};

export const SORT_FIELDS = [
  "priority",
  "run_out_date",
  "days_of_cover",
  "demand_per_day",
  "quantity",
  "order_cost",
  "product_name",
  "supplier_name",
] as const;
export type SortField = (typeof SORT_FIELDS)[number];
export type SortOrder = "asc" | "desc";

export const PAGE_SIZES = [10, 25, 50, 100] as const;
const DEFAULT_PAGE_SIZE = 25;
const MAX_SEARCH_LENGTH = 100;

export interface ReplenishmentQuery {
  view: View;
  priorities: Priority[];
  store: string | null;
  category: string | null;
  supplier: string | null;
  search: string;
  sort: SortField;
  order: SortOrder;
  page: number;
  pageSize: number;
}

export const DEFAULT_QUERY: ReplenishmentQuery = {
  view: "needs_action",
  priorities: [],
  store: null,
  category: null,
  supplier: null,
  search: "",
  sort: "priority",
  order: "asc",
  page: 1,
  pageSize: DEFAULT_PAGE_SIZE,
};

// Most useful direction first: soonest run-out and lowest cover first; biggest orders first.
const DESCENDING_FIRST = new Set<SortField>(["demand_per_day", "quantity", "order_cost"]);

type RawParams = Record<string, string | string[] | undefined>;

const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);
const all = (value: string | string[] | undefined) => (value === undefined ? [] : Array.isArray(value) ? value : [value]);

/** Unknown or malformed values fall back to defaults instead of erroring. */
export function parseQuery(params: RawParams): ReplenishmentQuery {
  const view = first(params.view);
  const sort = first(params.sort);
  const order = first(params.order);
  const page = Number.parseInt(first(params.page) ?? "", 10);
  const pageSize = Number.parseInt(first(params.page_size) ?? "", 10);
  const priorities = all(params.priority);
  return {
    view: VIEWS.includes(view as View) ? (view as View) : DEFAULT_QUERY.view,
    priorities: PRIORITIES.filter((p) => priorities.includes(p)),
    store: first(params.store_id) || null,
    category: first(params.category) || null,
    supplier: first(params.supplier_id) || null,
    search: (first(params.search) ?? "").slice(0, MAX_SEARCH_LENGTH),
    sort: SORT_FIELDS.includes(sort as SortField) ? (sort as SortField) : DEFAULT_QUERY.sort,
    order: order === "asc" || order === "desc" ? order : DEFAULT_QUERY.order,
    page: Number.isFinite(page) && page > 0 ? page : 1,
    pageSize: (PAGE_SIZES as readonly number[]).includes(pageSize) ? pageSize : DEFAULT_PAGE_SIZE,
  };
}

/** Scope filters shared by the plan and the list. */
export function toPlanParams(query: ReplenishmentQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.store) params.set("store_id", query.store);
  if (query.category) params.set("category", query.category);
  if (query.supplier) params.set("supplier_id", query.supplier);
  if (query.search.trim()) params.set("search", query.search.trim());
  return params;
}

/** Query string for the page URL (defaults omitted). */
export function toSearchParams(query: ReplenishmentQuery): URLSearchParams {
  const params = toPlanParams(query);
  if (query.view !== DEFAULT_QUERY.view) params.set("view", query.view);
  for (const p of query.priorities) params.append("priority", p);
  if (query.sort !== DEFAULT_QUERY.sort) params.set("sort", query.sort);
  if (query.order !== DEFAULT_QUERY.order) params.set("order", query.order);
  if (query.page !== 1) params.set("page", String(query.page));
  if (query.pageSize !== DEFAULT_PAGE_SIZE) params.set("page_size", String(query.pageSize));
  return params;
}

/** Query string for GET /api/v1/replenishment: the view becomes repeated action parameters. */
export function toListParams(query: ReplenishmentQuery): URLSearchParams {
  const params = toPlanParams(query);
  for (const action of VIEW_ACTIONS[query.view]) params.append("action", action);
  for (const p of query.priorities) params.append("priority", p);
  if (query.sort !== DEFAULT_QUERY.sort) params.set("sort", query.sort);
  if (query.order !== DEFAULT_QUERY.order) params.set("order", query.order);
  params.set("page", String(query.page));
  params.set("page_size", String(query.pageSize));
  return params;
}

export function hasActiveFilters(query: ReplenishmentQuery): boolean {
  return Boolean(query.store || query.category || query.supplier || query.search.trim() || query.priorities.length || query.view !== DEFAULT_QUERY.view);
}

export function nextSort(query: ReplenishmentQuery, field: SortField): Pick<ReplenishmentQuery, "sort" | "order"> {
  if (query.sort === field) return { sort: field, order: query.order === "asc" ? "desc" : "asc" };
  return { sort: field, order: DESCENDING_FIRST.has(field) ? "desc" : "asc" };
}

/** Links to the other pages for one position. */
export function positionLinks(row: { supplier_id: string; product_id: string; store_id: string; sku: string }) {
  return {
    supplier: `/suppliers/${encodeURIComponent(row.supplier_id)}`,
    stock: `/inventory?search=${encodeURIComponent(row.sku)}&store_id=${encodeURIComponent(row.store_id)}`,
    orders: `/purchase-orders?store_id=${encodeURIComponent(row.store_id)}&product_id=${encodeURIComponent(row.product_id)}`,
  };
}
