// Run with: npm test (Node 24's built-in test runner; it loads the TypeScript module directly).
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  DEFAULT_SUPPLIER_QUERY,
  hasActiveFilters,
  nextSort,
  parseSupplierQuery,
  productStockLink,
  supplierLinks,
  toSearchParams,
} from "../src/lib/suppliers/query.ts";

test("an empty URL gives the default query (most flags first)", () => {
  assert.deepEqual(parseSupplierQuery({}), DEFAULT_SUPPLIER_QUERY);
  assert.equal(toSearchParams(DEFAULT_SUPPLIER_QUERY).toString(), "");
});

test("URL parameters round-trip and use the API's names", () => {
  const url = "search=harbor&attention=true&sort=on_time_rate&order=asc";
  const query = parseSupplierQuery(Object.fromEntries(new URLSearchParams(url)));
  assert.deepEqual(query, { search: "harbor", attention: "flagged", sort: "on_time_rate", order: "asc" });
  assert.equal(toSearchParams(query).toString(), url);
  assert.equal(parseSupplierQuery({ attention: "false" }).attention, "clear");
  assert.equal(toSearchParams({ ...DEFAULT_SUPPLIER_QUERY, attention: "clear" }).toString(), "attention=false");
});

test("malformed values fall back to defaults", () => {
  const query = parseSupplierQuery({ attention: "maybe", sort: "risk_score", order: "up", search: "x".repeat(150) });
  assert.equal(query.attention, "all");
  assert.equal(query.sort, "attention");
  assert.equal(query.order, "desc");
  assert.equal(query.search.length, 100);
  assert.equal(parseSupplierQuery({ sort: ["spend", "orders"] }).sort, "spend");
});

test("sorting starts worst first, then toggles", () => {
  assert.deepEqual(nextSort(DEFAULT_SUPPLIER_QUERY, "on_time_rate"), { sort: "on_time_rate", order: "asc" });
  assert.deepEqual(nextSort(DEFAULT_SUPPLIER_QUERY, "overdue_orders"), { sort: "overdue_orders", order: "desc" });
  assert.deepEqual(nextSort(DEFAULT_SUPPLIER_QUERY, "supplier_name"), { sort: "supplier_name", order: "asc" });
  assert.deepEqual(nextSort(DEFAULT_SUPPLIER_QUERY, "attention"), { sort: "attention", order: "asc" });
  assert.equal(hasActiveFilters(DEFAULT_SUPPLIER_QUERY), false);
  assert.equal(hasActiveFilters({ ...DEFAULT_SUPPLIER_QUERY, attention: "flagged" }), true);
  assert.equal(hasActiveFilters({ ...DEFAULT_SUPPLIER_QUERY, search: "   " }), false);
});

test("cross-links are filtered to the supplier and safely encoded", () => {
  const links = supplierLinks("SUP-0005", "Harbor Supply Co");
  assert.equal(links.detail, "/suppliers/SUP-0005");
  assert.equal(links.orders, "/purchase-orders?supplier_id=SUP-0005");
  assert.equal(links.overdueOrders, "/purchase-orders?supplier_id=SUP-0005&overdue=true&sort=days_overdue");
  assert.equal(links.sales, "/sales?supplier_id=SUP-0005");
  assert.equal(links.stock, "/inventory?search=Harbor%20Supply%20Co");
  assert.equal(links.atRiskStock, "/inventory?search=Harbor%20Supply%20Co&status=out_of_stock&status=critical");
  assert.equal(supplierLinks("A/B&C", "X").detail, "/suppliers/A%2FB%26C");
  assert.equal(productStockLink("SKU-BAK-00187"), "/inventory?search=SKU-BAK-00187");
});
