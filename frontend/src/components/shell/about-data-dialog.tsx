"use client";

import { FlaskConical, X } from "lucide-react";
import { useId } from "react";

import { Dialog } from "@/components/ui/dialog";
import type { SnapshotMeta } from "@/lib/dashboard/types";
import { formatDateRange } from "@/lib/format";

const DEFINITIONS: Array<[string, string]> = [
  ["Inventory value", "End-of-day units on hand × unit cost, summed across stores."],
  ["Available", "Units on hand minus units reserved for open customer orders."],
  ["Low-stock product", "Network-wide available units at or below the sum of the store reorder points (and not a stockout risk)."],
  ["Stockout-risk product", "At least one store is below safety stock or out of stock."],
  ["Days of cover", "Available units ÷ average daily units sold over the last 14 days."],
  ["Forecast baseline", "Average of the same weekday over the last 4 weeks. A simple seasonal baseline, not a trained model."],
  ["On-time rate", "Share of purchase orders delivered in the last 30 days on or before the expected date."],
];

export function AboutDataDialog({ open, onClose, meta }: { open: boolean; onClose: () => void; meta: SnapshotMeta }) {
  const titleId = useId();
  return (
    <Dialog open={open} onClose={onClose} labelledBy={titleId}>
      <div className="max-h-[85dvh] overflow-y-auto p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="grid size-10 place-items-center rounded-xl bg-brand-soft text-brand">
              <FlaskConical aria-hidden className="size-5" />
            </span>
            <h2 id={titleId} className="text-lg font-semibold tracking-tight text-ink">
              About this data
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="grid size-8 place-items-center rounded-lg text-ink-muted hover:bg-slate-100 hover:text-ink"
          >
            <X aria-hidden className="size-4" />
          </button>
        </div>

        <p className="mt-4 text-sm leading-6 text-ink-muted">
          Every figure on this dashboard is <strong className="font-semibold text-ink">calculated from a synthetic retail dataset</strong>{" "}
          produced by the project&apos;s deterministic generator (seed {meta.seed}): {meta.stores.length} stores,{" "}
          {meta.categories.length} categories, {formatDateRange(meta.start_date, meta.end_date)}. They are not real business
          results, and no AI model is involved yet.
        </p>

        <dl className="mt-5 divide-y divide-line rounded-xl border border-line">
          {DEFINITIONS.map(([term, definition]) => (
            <div key={term} className="grid gap-1 px-4 py-3 sm:grid-cols-[10rem_1fr] sm:gap-4">
              <dt className="text-[13px] font-medium text-ink">{term}</dt>
              <dd className="text-[13px] leading-5 text-ink-muted">{definition}</dd>
            </div>
          ))}
        </dl>

        <p className="mt-5 text-xs leading-5 text-ink-subtle">
          Regenerate with <code className="rounded bg-slate-100 px-1 py-0.5 text-ink-muted">python scripts/export_dashboard_snapshot.py</code>{" "}
          from <code className="rounded bg-slate-100 px-1 py-0.5 text-ink-muted">backend/</code>. Databricks is not used by this page.
        </p>
      </div>
    </Dialog>
  );
}
