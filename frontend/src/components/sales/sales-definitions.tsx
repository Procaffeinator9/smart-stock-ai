"use client";

import { motion } from "motion/react";

import { cardClassName, fadeUp } from "@/components/ui/card";
import { cn } from "@/lib/cn";

// Mirrors backend/app/analytics/sales.py.
const DEFINITIONS: Array<[string, string]> = [
  ["Revenue", "Units sold × the price charged, summed. Each sales row is one store's daily total for one product."],
  ["Gross margin", "Revenue minus units × the product's standard unit cost (the data has one cost per product, the same as on purchase orders)."],
  ["Average price", "Revenue ÷ units sold."],
  ["Previous period", "The same number of days immediately before the selected range. Shown only when the data covers all of it."],
  ["Promotional share", "Revenue (or units) sold on promotion ÷ all revenue (or units)."],
  ["Average discount", "1 − promotional revenue ÷ the same units at list price."],
  [
    "Measured uplift",
    "For products promoted in the period: average units per store-day on promotion ÷ at the regular price − 1. Only store-days with at least one sale count, and sales are capped by stock on hand, so this understates true demand uplift.",
  ],
  ["Stockout days", "Store-days that ended with no available units (on hand − reserved ≤ 0). Not affected by the promotion filter."],
];

/** How the Sales page's figures are calculated (linked from the data notice). */
export function SalesDefinitions() {
  return (
    <motion.section
      variants={fadeUp}
      id="sales-definitions"
      aria-labelledby="sales-definitions-title"
      className={cn(cardClassName, "scroll-mt-24 p-5")}
    >
      <h2 id="sales-definitions-title" className="text-[15px] font-semibold tracking-tight text-ink">
        How these figures are calculated
      </h2>
      <p className="mt-1 text-[13px] leading-5 text-ink-muted">
        Calculated from the synthetic retail dataset; not real business results. Sales rows are daily totals per store and product, so
        transactions, basket size, and average order value aren&apos;t available. Demand forecasting stays on the Overview.
      </p>
      <dl className="mt-4 grid gap-x-6 divide-y divide-line rounded-xl border border-line lg:grid-cols-2 lg:divide-y-0">
        {DEFINITIONS.map(([term, definition]) => (
          <div key={term} className="grid gap-1 px-4 py-3 sm:grid-cols-[9.5rem_1fr] sm:gap-4">
            <dt className="text-[13px] font-medium text-ink">{term}</dt>
            <dd className="text-[13px] leading-5 text-ink-muted">{definition}</dd>
          </div>
        ))}
      </dl>
    </motion.section>
  );
}
