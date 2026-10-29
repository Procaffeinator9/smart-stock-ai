"use client";

import { ArrowRight, CircleCheck } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";

import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { StatusBadge } from "@/components/ui/status-badge";
import { StockMeter } from "@/components/ui/stock-meter";
import { cn } from "@/lib/cn";
import type { InventoryAlert, InventorySummary } from "@/lib/dashboard/types";
import { daysBetween, formatInteger, formatShortDate, formatStore } from "@/lib/format";

interface InventoryAlertsCardProps {
  alerts: InventoryAlert[];
  positions: InventorySummary["positions"];
  asOf: string;
  className?: string;
}

function deliveryLabel(nextDelivery: string | null, asOf: string): { text: string; tone: string } {
  if (!nextDelivery) return { text: "No open PO", tone: "text-red-700" };
  const days = daysBetween(asOf, nextDelivery);
  if (days < 0) return { text: `PO overdue ${-days}d`, tone: "text-red-700" };
  if (days === 0) return { text: "PO due today", tone: "text-amber-700" };
  return { text: `PO due ${formatShortDate(nextDelivery)}`, tone: "text-ink-muted" };
}

function AlertStockMeter({ alert }: { alert: InventoryAlert }) {
  return (
    <div className="w-full">
      <StockMeter
        available={alert.available}
        reorderPoint={alert.reorder_point}
        safetyStock={alert.safety_stock}
        status={alert.status}
      />
      <p className="mt-1 text-[11px] tabular-nums text-ink-subtle">
        {formatInteger(alert.available)} avail. · safety {alert.safety_stock} · reorder {alert.reorder_point}
      </p>
    </div>
  );
}

export function InventoryAlertsCard({ alerts, positions, asOf, className }: InventoryAlertsCardProps) {
  const atRisk = positions.out_of_stock + positions.critical;
  return (
    <Card
      title="Top inventory alerts"
      description={`Most urgent store positions of ${formatInteger(atRisk)} at stockout risk, as of ${formatShortDate(asOf)}`}
      className={className}
      bodyClassName="px-0 pb-2"
      footer={
        <Link
          href="/inventory?status=out_of_stock&status=critical"
          className="inline-flex items-center gap-1 text-xs font-medium text-brand hover:text-brand-strong"
        >
          View all {formatInteger(atRisk)} in Inventory
          <ArrowRight aria-hidden className="size-3.5" />
        </Link>
      }
      action={
        <div className="flex gap-1.5 text-[11px] font-medium">
          <span className="rounded-full bg-red-100 px-2 py-0.5 text-red-800">{positions.out_of_stock} out</span>
          <span className="rounded-full bg-red-50 px-2 py-0.5 text-red-700">{positions.critical} below safety</span>
        </div>
      }
    >
      {alerts.length === 0 ? (
        <EmptyState icon={CircleCheck} title="No stock alerts" description="Every store position is above its reorder point." />
      ) : (
        <ul className="divide-y divide-line">
          {alerts.map((alert, index) => {
            const delivery = deliveryLabel(alert.next_delivery, asOf);
            return (
              <motion.li
                key={`${alert.store_id}-${alert.product_id}`}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.15 + index * 0.04, duration: 0.3 }}
                className="grid grid-cols-1 gap-x-4 gap-y-2 px-5 py-3 transition-colors hover:bg-slate-50/70 sm:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_auto] sm:items-center"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truncate text-sm font-medium text-ink">{alert.product_name}</p>
                    <StatusBadge status={alert.status} />
                  </div>
                  <p className="mt-0.5 truncate text-xs text-ink-subtle">
                    {formatStore(alert.store_id)} · {alert.sku} · {alert.supplier_name}
                  </p>
                </div>
                <AlertStockMeter alert={alert} />
                <div className="text-xs sm:text-right">
                  <p className={cn("font-medium", delivery.tone)}>{delivery.text}</p>
                  <p className="text-ink-subtle">
                    {alert.days_of_cover === null ? "No recent sales" : `${alert.days_of_cover.toFixed(1)} days of cover`}
                  </p>
                </div>
              </motion.li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
