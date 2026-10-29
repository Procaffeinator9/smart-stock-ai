// Run with: npm test (Node 24's built-in test runner; it loads the TypeScript module directly).
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  DEFAULT_PO_QUERY,
  hasActiveFilters,
  nextSort,
  overdueView,
  parsePurchaseOrderQuery,
  toListParams,
  toSearchParams,
  toSummaryParams,
} from "../src/lib/purchase-orders/query.ts";

const parse = (qs) => {
  const params = {};
  for (const [key, value] of new URLSearchParams(qs)) params[key] = key in params ? [].concat(params[key], value) : value;
  return parsePurchaseOrderQuery(params);
};

test("an empty URL gives the default query (every order date, newest first)", () => {
  assert.deepEqual(parsePurchaseOrderQuery({}), DEFAULT_PO_QUERY);
  assert.equal(toSearchParams(DEFAULT_PO_QUERY).toString(), "");
  assert.equal(toSummaryParams(DEFAULT_PO_QUERY).toString(), "");
  assert.equal(toListParams(DEFAULT_PO_QUERY).toString(), "page=1&page_size=25");
});

test("URL parameters round-trip and use the API's names", () => {
  const url =
    "days=30&store_id=STR-002&supplier_id=SUP-0005&category=Dairy&product_id=PRD-00007&status=PLACED&status=IN_TRANSIT&overdue=true&search=po-12&sort=days_overdue&order=asc&page=2&page_size=50";
  const query = parse(url);
  assert.deepEqual(query, {
    ...DEFAULT_PO_QUERY,
    days: 30,
    store: "STR-002",
    supplier: "SUP-0005",
    category: "Dairy",
    product: "PRD-00007",
    status: ["PLACED", "IN_TRANSIT"],
    lateness: "overdue",
    search: "po-12",
    sort: "days_overdue",
    order: "asc",
    page: 2,
    pageSize: 50,
  });
  assert.equal(toSearchParams(query).toString(), url);
  // The summary takes only the scope filters: status, lateness, search, sort and page narrow the table.
  assert.equal(toSummaryParams(query).toString(), "days=30&store_id=STR-002&supplier_id=SUP-0005&category=Dairy&product_id=PRD-00007");
});

test("delivered-late view and a custom order-date range", () => {
  const late = parse("delivered_late=true");
  assert.equal(late.lateness, "late");
  assert.equal(toSearchParams(late).toString(), "delivered_late=true");

  const custom = parse("days=7&date_from=2026-02-01&date_to=2026-02-14");
  assert.equal(custom.days, null); // a custom range replaces the preset
  assert.equal(toSummaryParams(custom).toString(), "date_from=2026-02-01&date_to=2026-02-14");
});

test("malformed values fall back to defaults; statuses keep a fixed order", () => {
  const query = parse("days=45&date_from=2026-02-31&status=LOST&status=DELIVERED&status=PLACED&overdue=yes&sort=supplier&order=up&page=0&page_size=7");
  assert.equal(query.days, null);
  assert.equal(query.from, null);
  assert.deepEqual(query.status, ["PLACED", "DELIVERED"]);
  assert.equal(query.lateness, "all");
  assert.equal(query.sort, "order_date");
  assert.equal(query.order, "desc");
  assert.equal(query.page, 1);
  assert.equal(query.pageSize, 25);
  assert.equal(parse(`search=${"x".repeat(150)}`).search.length, 100);
});

test("active filters, sorting, and the overdue view", () => {
  assert.equal(hasActiveFilters(DEFAULT_PO_QUERY), false);
  assert.equal(hasActiveFilters({ ...DEFAULT_PO_QUERY, days: 30 }), false); // the window is not a filter
  assert.equal(hasActiveFilters({ ...DEFAULT_PO_QUERY, status: ["CANCELLED"] }), true);
  assert.equal(hasActiveFilters({ ...DEFAULT_PO_QUERY, lateness: "late" }), true);

  assert.deepEqual(nextSort(DEFAULT_PO_QUERY, "order_date"), { sort: "order_date", order: "asc" });
  assert.deepEqual(nextSort(DEFAULT_PO_QUERY, "value"), { sort: "value", order: "desc" });
  assert.deepEqual(nextSort(DEFAULT_PO_QUERY, "purchase_order_id"), { sort: "purchase_order_id", order: "asc" });

  const view = overdueView({ ...DEFAULT_PO_QUERY, store: "STR-001", status: ["DELIVERED"], search: "x", page: 4 });
  assert.equal(toSearchParams(view).toString(), "store_id=STR-001&overdue=true&sort=days_overdue");
});
