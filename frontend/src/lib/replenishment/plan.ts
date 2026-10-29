// The simulated reorder plan in the browser: totals for the lines a user keeps, and a CSV file to
// download. Nothing is sent anywhere. No runtime imports, so the tests in frontend/tests can load
// this file directly.
import type { SimulatedPlan } from "./types";

export interface PlanTotals {
  lines: number;
  units: number;
  /** In dollars, summed in cents so floating point never drifts. */
  cost: number;
  shelfLifeWarnings: number;
  bySupplier: Record<string, { lines: number; units: number; cost: number }>;
}

/** Totals for the included lines (every line not in ``excluded``). */
export function planTotals(plan: SimulatedPlan, excluded: ReadonlySet<string>): PlanTotals {
  let lines = 0;
  let units = 0;
  let cents = 0;
  let shelfLifeWarnings = 0;
  const bySupplier: PlanTotals["bySupplier"] = {};
  for (const group of plan.suppliers) {
    let gLines = 0;
    let gUnits = 0;
    let gCents = 0;
    for (const item of group.items) {
      if (excluded.has(item.position_id)) continue;
      gLines += 1;
      gUnits += item.quantity;
      gCents += Math.round(item.order_cost * 100);
      if (item.exceeds_shelf_life) shelfLifeWarnings += 1;
    }
    bySupplier[group.supplier_id] = { lines: gLines, units: gUnits, cost: gCents / 100 };
    lines += gLines;
    units += gUnits;
    cents += gCents;
  }
  return { lines, units, cost: cents / 100, shelfLifeWarnings, bySupplier };
}

const CSV_COLUMNS = [
  "supplier_id",
  "supplier_name",
  "store_id",
  "product_id",
  "sku",
  "product_name",
  "category",
  "priority",
  "quantity",
  "minimum_order_quantity",
  "raised_to_moq",
  "unit_cost",
  "estimated_cost",
  "expected_arrival",
  "estimated_demand_per_day",
  "demand_basis",
  "shelf_life_days",
  "shelf_life_conflict",
] as const;

/**
 * One CSV field: quoted when it contains a comma, quote or line break (quotes doubled), and with a
 * leading apostrophe when it starts like a spreadsheet formula (=, +, -, @, tab, carriage return),
 * so opening the file can never run a formula. Numbers are written as plain numbers.
 */
export function csvField(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "";
  if (typeof value === "boolean") return value ? "yes" : "no";
  let text = value;
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

/** The included lines as CSV (header first, CRLF line endings), most urgent first within each supplier. */
export function planCsv(plan: SimulatedPlan, excluded: ReadonlySet<string>): string {
  const rows: string[] = [CSV_COLUMNS.join(",")];
  for (const group of plan.suppliers) {
    for (const item of group.items) {
      if (excluded.has(item.position_id)) continue;
      rows.push(
        [
          item.supplier_id,
          item.supplier_name,
          item.store_id,
          item.product_id,
          item.sku,
          item.product_name,
          item.category,
          item.priority,
          item.quantity,
          item.minimum_order_quantity,
          item.raised_to_moq,
          item.unit_cost,
          item.order_cost,
          item.expected_arrival,
          item.demand_per_day,
          item.demand_basis,
          item.shelf_life_days,
          item.exceeds_shelf_life,
        ]
          .map(csvField)
          .join(","),
      );
    }
  }
  return `${rows.join("\r\n")}\r\n`;
}

/** File name for the download, e.g. simulated-reorder-plan-2026-03-31.csv. */
export function planFileName(asOf: string): string {
  return `simulated-reorder-plan-${asOf.replace(/[^0-9-]/g, "")}.csv`;
}
