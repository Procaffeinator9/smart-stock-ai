// Run with: npm test (Node 24's built-in test runner; it loads the TypeScript modules directly).
import assert from "node:assert/strict";
import { test } from "node:test";

import { csvField, planCsv, planFileName, planTotals } from "../src/lib/replenishment/plan.ts";
import {
  DEFAULT_QUERY,
  hasActiveFilters,
  nextSort,
  parseQuery,
  positionLinks,
  toListParams,
  toPlanParams,
  toSearchParams,
} from "../src/lib/replenishment/query.ts";

const parse = (qs) => {
  const params = {};
  for (const [key, value] of new URLSearchParams(qs)) params[key] = key in params ? [].concat(params[key], value) : value;
  return parseQuery(params);
};

test("an empty URL gives the default view: Order now + Expedite, most urgent first", () => {
  assert.deepEqual(parseQuery({}), DEFAULT_QUERY);
  assert.equal(toSearchParams(DEFAULT_QUERY).toString(), "");
  assert.equal(toPlanParams(DEFAULT_QUERY).toString(), "");
  assert.equal(toListParams(DEFAULT_QUERY).toString(), "action=order&action=expedite&page=1&page_size=25");
});

test("URL parameters round-trip; the view becomes action parameters for the API", () => {
  const url = "store_id=STR-002&category=Dairy&supplier_id=SUP-0005&search=milk&view=all&priority=critical&priority=high&sort=order_cost&order=desc&page=2&page_size=50";
  const query = parse(url);
  assert.deepEqual(query, {
    view: "all",
    priorities: ["critical", "high"],
    store: "STR-002",
    category: "Dairy",
    supplier: "SUP-0005",
    search: "milk",
    sort: "order_cost",
    order: "desc",
    page: 2,
    pageSize: 50,
  });
  assert.equal(toSearchParams(query).toString(), url);
  assert.equal(toPlanParams(query).toString(), "store_id=STR-002&category=Dairy&supplier_id=SUP-0005&search=milk");
  assert.equal(
    toListParams(query).toString(),
    "store_id=STR-002&category=Dairy&supplier_id=SUP-0005&search=milk&action=order&action=expedite&action=watch&priority=critical&priority=high&sort=order_cost&order=desc&page=2&page_size=50",
  );
  assert.equal(toListParams(parse("view=watch")).toString(), "action=watch&page=1&page_size=25");
});

test("malformed values fall back to defaults; priorities keep a fixed order", () => {
  const query = parse("view=everything&priority=low&priority=urgent&priority=critical&sort=risk&order=up&page=-1&page_size=7");
  assert.equal(query.view, "needs_action");
  assert.deepEqual(query.priorities, ["critical", "low"]);
  assert.equal(query.sort, "priority");
  assert.equal(query.order, "asc");
  assert.equal(query.page, 1);
  assert.equal(query.pageSize, 25);
  assert.equal(parse(`search=${"x".repeat(150)}`).search.length, 100);
});

test("active filters, sorting directions and cross-links", () => {
  assert.equal(hasActiveFilters(DEFAULT_QUERY), false);
  assert.equal(hasActiveFilters({ ...DEFAULT_QUERY, view: "watch" }), true);
  assert.equal(hasActiveFilters({ ...DEFAULT_QUERY, search: "  " }), false);
  assert.deepEqual(nextSort(DEFAULT_QUERY, "run_out_date"), { sort: "run_out_date", order: "asc" });
  assert.deepEqual(nextSort(DEFAULT_QUERY, "order_cost"), { sort: "order_cost", order: "desc" });
  assert.deepEqual(nextSort(DEFAULT_QUERY, "priority"), { sort: "priority", order: "desc" });
  assert.deepEqual(positionLinks({ supplier_id: "SUP-0005", product_id: "PRD-00007", store_id: "STR-001", sku: "SKU-DRY-00007" }), {
    supplier: "/suppliers/SUP-0005",
    stock: "/inventory?search=SKU-DRY-00007&store_id=STR-001",
    orders: "/purchase-orders?store_id=STR-001&product_id=PRD-00007",
  });
});

const item = (id, supplier, quantity, cost, extra = {}) => ({
  position_id: id,
  supplier_id: supplier,
  supplier_name: `Supplier ${supplier}`,
  store_id: "STR-001",
  product_id: id.split("|")[1],
  sku: `SKU-${id}`,
  product_name: `Product ${id}`,
  category: "Dairy",
  priority: "medium",
  quantity,
  minimum_order_quantity: 12,
  raised_to_moq: false,
  unit_cost: 0.1,
  order_cost: cost,
  expected_arrival: "2026-04-05",
  demand_per_day: 4,
  demand_basis: "last 14 days",
  shelf_life_days: null,
  exceeds_shelf_life: false,
  ...extra,
});

const plan = {
  lines: 3,
  units: 60,
  cost: 0.3,
  raised_to_moq: 0,
  shelf_life_warnings: 1,
  manual_review: 0,
  suppliers: [
    { supplier_id: "A", items: [item("STR-001|P1", "A", 10, 0.1), item("STR-001|P2", "A", 20, 0.1, { exceeds_shelf_life: true })] },
    { supplier_id: "B", items: [item("STR-001|P3", "B", 30, 0.1)] },
  ],
};

test("plan totals follow the included lines and sum in cents", () => {
  const all = planTotals(plan, new Set());
  assert.equal(all.lines, 3);
  assert.equal(all.units, 60);
  assert.equal(all.cost, 0.3); // 0.1 + 0.1 + 0.1 without floating-point drift
  assert.equal(all.shelfLifeWarnings, 1);
  assert.deepEqual(all.bySupplier.A, { lines: 2, units: 30, cost: 0.2 });

  const some = planTotals(plan, new Set(["STR-001|P2"]));
  assert.deepEqual([some.lines, some.units, some.cost, some.shelfLifeWarnings], [2, 40, 0.2, 0]);
  assert.deepEqual(planTotals(plan, new Set(["STR-001|P1", "STR-001|P2", "STR-001|P3"])).bySupplier.B, { lines: 0, units: 0, cost: 0 });
});

test("CSV fields are escaped and cannot run spreadsheet formulas", () => {
  assert.equal(csvField("plain"), "plain");
  assert.equal(csvField('Say "hi", world'), '"Say ""hi"", world"');
  assert.equal(csvField("line\nbreak"), '"line\nbreak"');
  assert.equal(csvField("=HYPERLINK(1)"), "'=HYPERLINK(1)");
  assert.equal(csvField("+1"), "'+1");
  assert.equal(csvField("-2"), "'-2");
  assert.equal(csvField("@SUM(A1)"), "'@SUM(A1)");
  assert.equal(csvField('=1,"x"'), `"'=1,""x"""`);
  assert.equal(csvField(-2), "-2"); // numbers are numbers
  assert.equal(csvField(null), "");
  assert.equal(csvField(true), "yes");
  assert.equal(csvField(Number.NaN), "");
});

test("the CSV has a header and only the included lines", () => {
  const csv = planCsv(plan, new Set(["STR-001|P2"]));
  const lines = csv.trimEnd().split("\r\n");
  assert.equal(lines.length, 3);
  assert.ok(lines[0].startsWith("supplier_id,supplier_name,store_id,product_id,sku,product_name"));
  assert.ok(lines[1].startsWith("A,Supplier A,STR-001,P1,"));
  assert.ok(lines[2].startsWith("B,Supplier B,STR-001,P3,"));
  assert.ok(csv.endsWith("\r\n"));
  assert.equal(planCsv(plan, new Set(["STR-001|P1", "STR-001|P2", "STR-001|P3"])).trimEnd().split("\r\n").length, 1);
  assert.equal(planFileName("2026-03-31"), "simulated-reorder-plan-2026-03-31.csv");
  assert.equal(planFileName("../x"), "simulated-reorder-plan-.csv");
});
