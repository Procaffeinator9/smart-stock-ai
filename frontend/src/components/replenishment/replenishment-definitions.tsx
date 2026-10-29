"use client";

import { motion } from "motion/react";

import { cardClassName, fadeUp } from "@/components/ui/card";
import { cn } from "@/lib/cn";
import type { ReplenishmentSettings } from "@/lib/replenishment/types";

/** How the Replenishment page's figures are calculated (mirrors backend/app/analytics/replenishment.py). */
export function ReplenishmentDefinitions({ settings }: { settings: ReplenishmentSettings }) {
  const definitions: Array<[string, string]> = [
    [
      "Estimated demand",
      `Units sold ÷ in-stock days over the last ${settings.demand_window_days} days. Days that start with no available stock are left out, with their sales. With fewer than ${settings.min_in_stock_days} in-stock days the window widens to ${settings.fallback_window_days.join(", then ")} days, then falls back to (reorder point − safety stock) ÷ stated lead time (low confidence). The data only has end-of-day stock, so a day that sells out part-way still counts: this is an estimate, not measured demand.`,
    ],
    ["Inventory position", "Available (on hand − reserved) + units on open orders, including overdue ones, as on the Inventory page."],
    ["Order now", "Inventory position at or below the reorder point."],
    [
      "Recommended quantity",
      `Target = reorder point + ⌈demand × ${settings.review_days}⌉; need = target − inventory position; quantity = the larger of the need and the supplier's minimum order (no pack-size rounding). No quantity without recent demand.`,
    ],
    ["Estimated cost", "Quantity × the product's unit cost."],
    ["Expected arrival", "As-of date + the supplier's stated lead time. Observed lead time and on-time rate are shown as context."],
    [
      "Expedite",
      "Out of stock or below safety stock with an open order that was due on or before the as-of date and hadn't arrived by that end-of-day snapshot, or that is expected after the projected run-out. No duplicate order is suggested.",
    ],
    ["Watch", `Above the reorder point but projected to reach it within ${settings.watch_days} days. Hidden unless you choose Watch or All.`],
    [
      "Priority",
      "Critical: out of stock, or below safety stock with nothing arriving before the projected run-out. High: below safety stock with stock arriving in time, or an order is needed and stock runs out before a new order could arrive. Medium: an order is needed. Low: watch.",
    ],
    [
      "Run-out and days without stock",
      "Run-out = as-of date + ⌊available ÷ demand⌋. Days without stock = from the run-out to the next expected delivery. Both are projections; lost sales and lost revenue are not estimated.",
    ],
    ["Shelf life", "Flagged when the stock after ordering would last longer than the product keeps. Quantities are not capped."],
  ];

  return (
    <motion.section
      variants={fadeUp}
      id="replenishment-definitions"
      aria-labelledby="replenishment-definitions-title"
      className={cn(cardClassName, "scroll-mt-24 p-5")}
    >
      <h2 id="replenishment-definitions-title" className="text-[15px] font-semibold tracking-tight text-ink">
        How these figures are calculated
      </h2>
      <p className="mt-1 text-[13px] leading-5 text-ink-muted">
        Calculated from the synthetic retail dataset on its as-of date (the latest inventory snapshot), not today. Recommendations are a
        read-only simulation: nothing is ordered. The data has no pack sizes, price breaks, store transfers or lost-sales records. In this
        data the business already reorders automatically, so most urgent positions are already on order and need chasing rather than a new
        order.
      </p>
      <dl className="mt-4 grid gap-x-6 divide-y divide-line rounded-xl border border-line lg:grid-cols-2 lg:divide-y-0">
        {definitions.map(([term, definition]) => (
          <div key={term} className="grid gap-1 px-4 py-3 sm:grid-cols-[9.5rem_1fr] sm:gap-4">
            <dt className="text-[13px] font-medium text-ink">{term}</dt>
            <dd className="text-[13px] leading-5 text-ink-muted">{definition}</dd>
          </div>
        ))}
      </dl>
    </motion.section>
  );
}
