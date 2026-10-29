"use client";

import { ClipboardList } from "lucide-react";
import { useState } from "react";

import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PurchaseOrderBadge } from "@/components/ui/status-badge";
import { SegmentedControl } from "@/components/ui/segmented-control";
import type { PurchaseOrderRow, PurchaseOrderSummary } from "@/lib/dashboard/types";
import { formatCurrency, formatInteger, formatPercent, formatShortDate, formatStore } from "@/lib/format";

type View = "latest" | "overdue";
const COLLAPSED_ROWS = 6;

interface PurchaseOrdersCardProps {
  summary: PurchaseOrderSummary;
  recent: PurchaseOrderRow[];
  overdue: PurchaseOrderRow[];
  className?: string;
}

export function PurchaseOrdersCard({ summary, recent, overdue, className }: PurchaseOrdersCardProps) {
  const [view, setView] = useState<View>("latest");
  const [expanded, setExpanded] = useState(false);
  const rows = view === "latest" ? recent : overdue;
  const visible = expanded ? rows : rows.slice(0, COLLAPSED_ROWS);

  const stats: Array<[string, string]> = [
    ["Open orders", formatInteger(summary.open)],
    ["Overdue", formatInteger(summary.overdue)],
    ["On time, last 30 days", summary.on_time_rate_last_30_days === null ? "—" : formatPercent(summary.on_time_rate_last_30_days)],
  ];

  return (
    <Card
      title="Purchase orders"
      description="Replenishment orders placed with suppliers"
      className={className}
      bodyClassName="px-0 pb-0"
      action={
        <SegmentedControl
          label="Purchase order view"
          options={[
            { value: "latest", label: `Latest ${recent.length}` },
            { value: "overdue", label: `Overdue ${overdue.length}` },
          ]}
          value={view}
          onChange={(next) => {
            setView(next);
            setExpanded(false);
          }}
        />
      }
    >
      <dl className="mx-5 mb-4 grid grid-cols-3 divide-x divide-line rounded-xl border border-line bg-slate-50/60">
        {stats.map(([label, value]) => (
          <div key={label} className="px-3 py-2.5">
            <dt className="truncate text-[11px] text-ink-subtle">{label}</dt>
            <dd className="text-base font-semibold tabular-nums text-ink">{value}</dd>
          </div>
        ))}
      </dl>

      {rows.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title={view === "overdue" ? "No overdue orders" : "No purchase orders yet"}
          description={view === "overdue" ? "Every open order is still within its expected delivery date." : undefined}
        />
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-[13px]">
              <caption className="sr-only">
                {view === "latest" ? "Most recent purchase orders" : "Open purchase orders past their expected delivery date"}
              </caption>
              <thead>
                <tr className="border-y border-line bg-slate-50/60 text-[11px] uppercase tracking-wide text-ink-subtle">
                  <th scope="col" className="px-5 py-2 font-medium">Order</th>
                  <th scope="col" className="px-3 py-2 font-medium">Product</th>
                  <th scope="col" className="px-3 py-2 font-medium">Store</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Qty</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Value</th>
                  <th scope="col" className="px-3 py-2 font-medium">Expected</th>
                  <th scope="col" className="px-5 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {visible.map((po) => (
                  <tr key={po.purchase_order_id} className="transition-colors hover:bg-slate-50/70">
                    <td className="px-5 py-2.5">
                      <p className="font-mono text-xs text-ink">{po.purchase_order_id}</p>
                      <p className="text-xs text-ink-subtle">{formatShortDate(po.order_date)}</p>
                    </td>
                    <td className="max-w-[220px] px-3 py-2.5">
                      <p className="truncate font-medium text-ink">{po.product_name}</p>
                      <p className="truncate text-xs text-ink-subtle">{po.supplier_name}</p>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-ink-muted">{formatStore(po.store_id)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-ink">{formatInteger(po.quantity)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-ink">{formatCurrency(po.value)}</td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-ink-muted">{formatShortDate(po.expected_delivery_date)}</td>
                    <td className="px-5 py-2.5">
                      <div className="flex items-center gap-1.5">
                        <PurchaseOrderBadge status={po.status} />
                        {po.is_late && (
                          <span className="rounded-full bg-red-50 px-1.5 py-0.5 text-[11px] font-medium text-red-700 ring-1 ring-inset ring-red-600/15">
                            Late
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rows.length > COLLAPSED_ROWS && (
            <div className="border-t border-line px-5 py-2.5">
              <button
                type="button"
                onClick={() => setExpanded((value) => !value)}
                aria-expanded={expanded}
                className="text-xs font-medium text-brand hover:text-brand-strong"
              >
                {expanded ? "Show fewer" : `Show all ${rows.length}`}
              </button>
            </div>
          )}
        </>
      )}
    </Card>
  );
}
