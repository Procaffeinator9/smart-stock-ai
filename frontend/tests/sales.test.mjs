// Run with: npm test (Node 24's built-in test runner; it loads the TypeScript modules directly).
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  DEFAULT_SALES_QUERY,
  hasActiveFilters,
  isoDateOrNull,
  nextSort,
  parseSalesQuery,
  toProductParams,
  toSearchParams,
  toSummaryParams,
} from "../src/lib/sales/query.ts";
import { trendPoints } from "../src/lib/sales/series.ts";

test("an empty URL gives the default query (last 30 days, revenue high to low)", () => {
  assert.deepEqual(parseSalesQuery({}), DEFAULT_SALES_QUERY);
  assert.equal(toSearchParams(DEFAULT_SALES_QUERY).toString(), "");
  assert.equal(toSummaryParams(DEFAULT_SALES_QUERY).toString(), "");
  assert.equal(toProductParams(DEFAULT_SALES_QUERY).toString(), "page=1&page_size=25");
});

test("URL parameters round-trip and use the API's names", () => {
  const url =
    "days=7&store_id=STR-002&category=Dairy&supplier_id=SUP-0005&promotion=true&search=milk&sort=units&order=asc&page=3&page_size=50";
  const query = parseSalesQuery(Object.fromEntries(new URLSearchParams(url)));
  assert.deepEqual(query, {
    ...DEFAULT_SALES_QUERY,
    days: 7,
    store: "STR-002",
    category: "Dairy",
    supplier: "SUP-0005",
    promotion: "promo",
    search: "milk",
    sort: "units",
    order: "asc",
    page: 3,
    pageSize: 50,
  });
  assert.equal(toSearchParams(query).toString(), url);
  // The summary only needs the window and filters, not the table's search, sort, or page.
  assert.equal(toSummaryParams(query).toString(), "days=7&store_id=STR-002&category=Dairy&supplier_id=SUP-0005&promotion=true");
  assert.equal(parseSalesQuery({ promotion: "false" }).promotion, "regular");
});

test("a custom date range replaces the preset window", () => {
  const query = parseSalesQuery({ days: "90", date_from: "2026-02-01", date_to: "2026-02-14" });
  assert.equal(query.from, "2026-02-01");
  assert.equal(query.to, "2026-02-14");
  assert.equal(toSummaryParams(query).toString(), "date_from=2026-02-01&date_to=2026-02-14");
});

test("malformed values fall back to defaults instead of erroring", () => {
  const query = parseSalesQuery({
    days: "45",
    date_from: "2026-02-30",
    date_to: "yesterday",
    promotion: "maybe",
    sort: "price; drop",
    order: "sideways",
    page: "-2",
    page_size: "1000",
    search: "x".repeat(150),
  });
  assert.equal(query.days, 30);
  assert.equal(query.from, null);
  assert.equal(query.to, null);
  assert.equal(query.promotion, "all");
  assert.equal(query.sort, "revenue");
  assert.equal(query.order, "desc");
  assert.equal(query.page, 1);
  assert.equal(query.pageSize, 25);
  assert.equal(query.search.length, 100);
  assert.equal(isoDateOrNull("2026-03-31"), "2026-03-31");
  assert.equal(isoDateOrNull("2026-3-31"), null);
});

test("repeated parameters use the first value", () => {
  assert.equal(parseSalesQuery({ store_id: ["STR-001", "STR-002"] }).store, "STR-001");
});

test("active filters and sort toggling", () => {
  assert.equal(hasActiveFilters(DEFAULT_SALES_QUERY), false);
  assert.equal(hasActiveFilters({ ...DEFAULT_SALES_QUERY, days: 7 }), false); // the window is not a filter
  assert.equal(hasActiveFilters({ ...DEFAULT_SALES_QUERY, promotion: "regular" }), true);
  assert.equal(hasActiveFilters({ ...DEFAULT_SALES_QUERY, search: "  " }), false);

  assert.deepEqual(nextSort(DEFAULT_SALES_QUERY, "revenue"), { sort: "revenue", order: "asc" });
  assert.deepEqual(nextSort(DEFAULT_SALES_QUERY, "units"), { sort: "units", order: "desc" });
  assert.deepEqual(nextSort(DEFAULT_SALES_QUERY, "product_name"), { sort: "product_name", order: "asc" });
});

const daily = {
  // Thu 2026-01-01 .. Tue 2026-01-13
  dates: Array.from({ length: 13 }, (_, i) => `2026-01-${String(i + 1).padStart(2, "0")}`),
  revenue: Array.from({ length: 13 }, (_, i) => 100.1 + i),
  units: Array.from({ length: 13 }, (_, i) => 10 + i),
  gross_margin: Array.from({ length: 13 }, () => 30.05),
  promo_revenue: Array.from({ length: 13 }, (_, i) => (i % 2 ? 5 : 0)),
};

test("daily points mirror the series", () => {
  const points = trendPoints(daily, "daily");
  assert.equal(points.length, 13);
  assert.deepEqual(points[0], { start: "2026-01-01", end: "2026-01-01", days: 1, revenue: 100.1, units: 10, gross_margin: 30.05, promo_revenue: 0 });
});

test("weekly points start on Monday, keep partial weeks, and preserve totals", () => {
  const weeks = trendPoints(daily, "weekly");
  assert.deepEqual(
    weeks.map((w) => [w.start, w.end, w.days]),
    [
      ["2026-01-01", "2026-01-04", 4], // Thu-Sun: cut off by the period start
      ["2026-01-05", "2026-01-11", 7],
      ["2026-01-12", "2026-01-13", 2],
    ],
  );
  const sum = (values) => values.reduce((a, b) => a + b, 0);
  assert.equal(sum(weeks.map((w) => w.units)), sum(daily.units));
  assert.ok(Math.abs(sum(weeks.map((w) => w.revenue)) - sum(daily.revenue)) < 1e-6);
  assert.equal(weeks[0].gross_margin, 120.2); // rounded to cents, no float noise
  assert.deepEqual(trendPoints({ dates: [], revenue: [], units: [], gross_margin: [], promo_revenue: [] }, "weekly"), []);
});
