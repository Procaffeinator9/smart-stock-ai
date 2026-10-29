"use client";

import { ArrowRight, CircleCheck } from "lucide-react";

import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PurchaseOrderBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { formatCurrency, formatInteger, formatLongDate, formatShortDate, formatStore } from "@/lib/format";
import type { PurchaseOrderSummary } from "@/lib/purchase-orders/types";

interface OverdueOrdersCardProps {
  overdue: PurchaseOrderSummary["overdue"];
  asOf: string;
  onShowAll: () => void;
  className?: string;
}

const BUCKET_TONE = ["bg-amber-50 ring-amber-600/15", "bg-orange-50 ring-orange-600/15", "bg-red-50 ring-red-600/15", "bg-red-100 ring-red-700/20"];

/** Open orders past their promised date, most overdue first, with an aging breakdown. */
export function OverdueOrdersCard({ overdue, asOf, onShowAll, className }: OverdueOrdersCardProps) {
  const shown = overdue.top.length;
  return (
    <Card
      title="Overdue orders"
      description={`Open orders past their promised date as of ${formatLongDate(asOf)}, most overdue first`}
      className={className}
      action={
        overdue.orders > 0 && (
          <button
            type="button"
            onClick={onShowAll}
            className="inline-flex items-center gap-1 rounded-lg border border-line bg-white px-2.5 py-1 text-xs font-medium text-ink shadow-sm hover:border-line-strong"
          >
            Show all {formatInteger(overdue.orders)} in the table <ArrowRight aria-hidden className="size-3.5" />
          </button>
        )
      }
    >
      {overdue.orders === 0 ? (
        <EmptyState icon={CircleCheck} title="No overdue orders" description="Every open order is still within its promised date." className="py-8" />
      ) : (
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="Overdue orders by days overdue">
            {overdue.aging.map((bucket, i) => (
              <div key={bucket.label} className={cn("rounded-lg px-3 py-2 ring-1 ring-inset", bucket.orders ? BUCKET_TONE[i] : "bg-slate-50 ring-line/70")}>
                <dt className="text-[11px] text-ink-subtle">{bucket.label} overdue</dt>
                <dd className="text-sm font-semibold tabular-nums text-ink">
                  {formatInteger(bucket.orders)} <span className="text-xs font-normal text-ink-subtle">orders</span>
                </dd>
                <dd className="text-[11px] tabular-nums text-ink-subtle">{formatCurrency(bucket.value)}</dd>
              </div>
            ))}
          </dl>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-[13px]">
              <caption className="sr-only">
                {shown < overdue.orders ? `The ${shown} most overdue of ${overdue.orders} overdue orders` : "Overdue orders"}
              </caption>
              <thead>
                <tr className="border-b border-line text-[11px] uppercase tracking-wide text-ink-subtle">
                  <th scope="col" className="py-2 pr-3 font-medium">Order</th>
                  <th scope="col" className="px-3 py-2 font-medium">Product</th>
                  <th scope="col" className="px-3 py-2 font-medium">Promised</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Overdue</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Qty</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Value</th>
                  <th scope="col" className="py-2 pl-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {overdue.top.map((po) => (
                  <tr key={po.purchase_order_id} className="border-b border-line last:border-b-0">
                    <td className="py-2 pr-3">
                      <p className="font-mono text-xs text-ink">{po.purchase_order_id}</p>
                      <p className="text-[11px] text-ink-subtle">{formatStore(po.store_id)}</p>
                    </td>
                    <td className="max-w-[240px] px-3 py-2">
                      <p className="truncate font-medium text-ink">{po.product_name}</p>
                      <p className="truncate text-[11px] text-ink-subtle">{po.supplier_name}</p>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-ink-muted">{formatShortDate(po.expected_delivery_date)}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-right font-semibold tabular-nums text-red-700">
                      {formatInteger(po.days_overdue ?? 0)} {po.days_overdue === 1 ? "day" : "days"}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-ink-muted">{formatInteger(po.quantity_ordered)}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-ink">{formatCurrency(po.value)}</td>
                    <td className="py-2 pl-3">
                      <PurchaseOrderBadge status={po.order_status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {shown < overdue.orders && (
            <p className="text-xs text-ink-subtle">
              Showing the {shown} most overdue of {formatInteger(overdue.orders)}.
            </p>
          )}
        </div>
      )}
    </Card>
  );
}
