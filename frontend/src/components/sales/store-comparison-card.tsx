"use client";

import { Store } from "lucide-react";
import { motion } from "motion/react";

import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { formatCurrencyCompact, formatInteger, formatPercent, formatStore } from "@/lib/format";
import type { StoreSales } from "@/lib/sales/types";

import { ChangeText } from "./change-text";

interface StoreComparisonCardProps {
  stores: StoreSales[];
  hasPrevious: boolean;
  className?: string;
}

export function StoreComparisonCard({ stores, hasPrevious, className }: StoreComparisonCardProps) {
  const max = Math.max(0, ...stores.map((s) => s.revenue));

  return (
    <Card
      title="Revenue by store"
      description={hasPrevious ? "Share of revenue, margin rate, and change vs the previous period" : "Share of revenue and margin rate"}
      className={className}
    >
      {max === 0 ? (
        <EmptyState icon={Store} title="No store revenue for these filters" />
      ) : (
        <ul className="space-y-4">
          {stores.map((store, index) => (
            <li key={store.store_id}>
              <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                <p className="text-sm font-medium text-ink">{formatStore(store.store_id)}</p>
                <p className="text-xs text-ink-subtle">
                  <span className="font-semibold tabular-nums text-ink">{formatCurrencyCompact(store.revenue)}</span> ·{" "}
                  {formatPercent(store.share)} of revenue · {formatInteger(store.units)} units · margin{" "}
                  {store.margin_rate === null ? "—" : formatPercent(store.margin_rate)}
                  {hasPrevious && (
                    <>
                      {" "}
                      · <ChangeText change={store.change} fallback="no change data" />
                    </>
                  )}
                </p>
              </div>
              <div
                className="h-2 overflow-hidden rounded-full bg-slate-100"
                role="img"
                aria-label={`${formatStore(store.store_id)}: ${formatCurrencyCompact(store.revenue)}, ${formatPercent(store.share)} of revenue`}
              >
                {/* scaleX (a transform) so the OS reduce-motion setting skips this animation */}
                <motion.div
                  className="h-full origin-left rounded-full bg-brand"
                  style={{ width: `${(store.revenue / max) * 100}%` }}
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: 1 }}
                  transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1], delay: 0.15 + index * 0.06 }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
