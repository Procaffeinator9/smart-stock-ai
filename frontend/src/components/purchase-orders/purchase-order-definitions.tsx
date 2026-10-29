"use client";

import { motion } from "motion/react";

import { cardClassName, fadeUp } from "@/components/ui/card";
import { cn } from "@/lib/cn";

// Mirrors backend/app/analytics/purchase_orders.py.
const DEFINITIONS: Array<[string, string]> = [
  ["As of", "The dataset's latest inventory snapshot date. Lateness is judged on this date, not today's date."],
  ["Order value", "Quantity ordered × unit cost. Open orders are placed or in transit."],
  ["Overdue", "Open, and the promised delivery date is before the as-of date. Days overdue = as-of date − promised date."],
  ["Delivered late", "Delivered after the promised date. An order delivered on its promised date is on time."],
  [
    "On-time rate",
    "Delivered on or before the promised date ÷ (delivered + overdue open orders). Overdue orders are already late, so they count against the rate. The Overview's 30-day rate counts delivered orders only.",
  ],
  ["Cancellation rate", "Cancelled ÷ all orders, by order date. The data has no cancellation date or reason."],
  ["Inbound, next 14 days", "Open orders by promised date, from the as-of date through the following 13 days."],
  ["Weekly charts", "Weeks start on Monday. Delivery performance uses the promised date; orders placed use the order date."],
];

/** How the Purchase Orders page's figures are calculated (linked from the data notice). */
export function PurchaseOrderDefinitions() {
  return (
    <motion.section
      variants={fadeUp}
      id="purchase-order-definitions"
      aria-labelledby="purchase-order-definitions-title"
      className={cn(cardClassName, "scroll-mt-24 p-5")}
    >
      <h2 id="purchase-order-definitions-title" className="text-[15px] font-semibold tracking-tight text-ink">
        How these figures are calculated
      </h2>
      <p className="mt-1 text-[13px] leading-5 text-ink-muted">
        Calculated from the synthetic retail dataset; not real business results. Every order has a single line, receipts always match the
        quantity ordered, and prices always match the product&apos;s cost, so fill rate and price variance aren&apos;t shown.
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
