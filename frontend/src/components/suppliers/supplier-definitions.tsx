"use client";

import { motion } from "motion/react";

import { cardClassName, fadeUp } from "@/components/ui/card";
import { cn } from "@/lib/cn";

// Mirrors backend/app/analytics/suppliers.py (including the "Needs attention" thresholds).
const DEFINITIONS: Array<[string, string]> = [
  ["Stated reliability", "The reliability score in the supplier table. It is the supplier's stated figure, not a measurement."],
  [
    "Observed on-time rate",
    "Delivered on or before the promised date ÷ (delivered + overdue open orders), as on the Purchase Orders page. The sample size is that denominator.",
  ],
  ["Lead time", "Stated: the supplier table's lead time. Observed: average days from order to delivery for delivered orders."],
  ["Spend", "Quantity × unit cost of the supplier's orders, excluding cancelled orders."],
  ["Revenue", "Sales of the products this supplier supplies (each product has one supplier), over every sale date in the data."],
  [
    "Stockout days",
    "Store-days that ended with no available units for those products. A correlation only: stockouts also depend on demand and reorder settings, so they don't show that the supplier caused them.",
  ],
  ["At-risk stock", "Store positions of those products below safety stock or out of stock on the as-of date."],
  [
    "Needs attention",
    "Any of: on-time rate below 75% (20+ orders); 2+ overdue orders; observed lead time at least 1 day or 25% over stated; 15%+ of positions at risk; on-time rate down 10+ points in the last 30 days vs the 30 before (20+ orders each); on-time rate 4+ points below stated reliability (100+ orders). Simple rules, not a risk score or prediction.",
  ],
];

/** How the Suppliers pages' figures are calculated (linked from the data notice). */
export function SupplierDefinitions() {
  return (
    <motion.section
      variants={fadeUp}
      id="supplier-definitions"
      aria-labelledby="supplier-definitions-title"
      className={cn(cardClassName, "scroll-mt-24 p-5")}
    >
      <h2 id="supplier-definitions-title" className="text-[15px] font-semibold tracking-tight text-ink">
        How these figures are calculated
      </h2>
      <p className="mt-1 text-[13px] leading-5 text-ink-muted">
        Calculated from the synthetic retail dataset; not real business results. In this data the generator draws each supplier&apos;s
        delivery delays from its stated reliability, so observed and stated reliability track each other closely. Each product has a single
        supplier, so suppliers can&apos;t be compared on the same product, and there is no quality, pricing or contract data.
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
