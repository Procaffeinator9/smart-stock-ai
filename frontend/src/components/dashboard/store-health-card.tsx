"use client";

import { Store } from "lucide-react";
import { motion } from "motion/react";

import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { POSITION_STATUS } from "@/components/ui/status-badge";
import type { InventorySummary, PositionStatus, StoreHealth } from "@/lib/dashboard/types";
import { formatCurrencyCompact, formatInteger, formatPercent, formatStore } from "@/lib/format";

const ORDER: PositionStatus[] = ["healthy", "low", "critical", "out_of_stock"];

interface StoreHealthCardProps {
  stores: StoreHealth[];
  positions: InventorySummary["positions"];
  className?: string;
}

export function StoreHealthCard({ stores, positions, className }: StoreHealthCardProps) {
  const total = ORDER.reduce((sum, status) => sum + positions[status], 0);
  return (
    <Card
      title="Inventory health by store"
      description="Share of product positions by stock status"
      className={className}
      bodyClassName="flex flex-col"
      footer={
        <ul className="flex flex-wrap gap-x-4 gap-y-1">
          {ORDER.map((status) => (
            <li key={status} className="flex items-center gap-1.5">
              <span className={`size-2 rounded-full ${POSITION_STATUS[status].bar}`} />
              {POSITION_STATUS[status].label}
            </li>
          ))}
        </ul>
      }
    >
      {stores.length === 0 ? (
        <EmptyState icon={Store} title="No stores in the dataset" />
      ) : (
        <ul className="space-y-4">
          {stores.map((store, index) => {
            const healthyShare = store.positions ? store.healthy / store.positions : 0;
            const description = ORDER.map((s) => `${store[s]} ${POSITION_STATUS[s].label.toLowerCase()}`).join(", ");
            return (
              <li key={store.store_id}>
                <div className="mb-1.5 flex items-baseline justify-between gap-3">
                  <p className="text-sm font-medium text-ink">{formatStore(store.store_id)}</p>
                  <p className="text-xs text-ink-subtle">
                    <span className="font-semibold tabular-nums text-ink">{formatPercent(healthyShare)}</span> healthy ·{" "}
                    {formatCurrencyCompact(store.inventory_value)}
                  </p>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-100" role="img" aria-label={`${formatStore(store.store_id)}: ${description}`}>
                  {/* scaleX (a transform) so the OS reduce-motion setting skips this animation */}
                  <motion.div
                    className="flex h-full origin-left"
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: 1 }}
                    transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1], delay: 0.15 + index * 0.06 }}
                  >
                    {ORDER.map((status) =>
                      store[status] > 0 ? (
                        <span
                          key={status}
                          className={`h-full ${POSITION_STATUS[status].bar}`}
                          style={{ width: `${(store[status] / store.positions) * 100}%` }}
                          title={`${POSITION_STATUS[status].label}: ${store[status]}`}
                        />
                      ) : null,
                    )}
                  </motion.div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {total > 0 && (
        <div className="mt-auto pt-6">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-subtle">
            All stores · {formatInteger(total)} positions
          </p>
          <dl className="grid grid-cols-2 gap-2">
            {ORDER.map((status) => (
              <div key={status} className="rounded-lg bg-slate-50 px-3 py-2 ring-1 ring-inset ring-line/70">
                <dt className="flex items-center gap-1.5 text-[11px] text-ink-subtle">
                  <span className={`size-1.5 rounded-full ${POSITION_STATUS[status].bar}`} />
                  {POSITION_STATUS[status].label}
                </dt>
                <dd className="text-sm font-semibold tabular-nums text-ink">
                  {formatInteger(positions[status])}
                  <span className="ml-1 text-xs font-normal text-ink-subtle">{formatPercent(positions[status] / total)}</span>
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </Card>
  );
}
