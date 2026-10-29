"use client";

import { ArrowUpRight } from "lucide-react";
import Link from "next/link";

import { lateness } from "@/components/purchase-orders/purchase-order-table";
import { Card } from "@/components/ui/card";
import { PurchaseOrderBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { formatCurrency, formatInteger, formatShortDate, formatStore } from "@/lib/format";
import type { PurchaseOrder } from "@/lib/purchase-orders/types";
import type { supplierLinks } from "@/lib/suppliers/query";

function OrderTable({ caption, orders }: { caption: string; orders: PurchaseOrder[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[820px] text-left text-[13px]">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-line text-[11px] uppercase tracking-wide text-ink-subtle">
            <th scope="col" className="py-2 pr-3 font-medium">Order</th>
            <th scope="col" className="px-3 py-2 font-medium">Product</th>
            <th scope="col" className="px-3 py-2 font-medium">Status</th>
            <th scope="col" className="px-3 py-2 font-medium">Ordered</th>
            <th scope="col" className="px-3 py-2 font-medium">Promised</th>
            <th scope="col" className="px-3 py-2 font-medium">Lateness</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Qty</th>
            <th scope="col" className="py-2 pl-3 text-right font-medium">Value</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((po) => {
            const late = lateness(po);
            return (
              <tr key={po.purchase_order_id} className="border-b border-line last:border-b-0">
                <td className="py-2 pr-3">
                  <p className="font-mono text-xs text-ink">{po.purchase_order_id}</p>
                  <p className="text-[11px] text-ink-subtle">{formatStore(po.store_id)}</p>
                </td>
                <td className="max-w-[240px] px-3 py-2">
                  <p className="truncate font-medium text-ink">{po.product_name}</p>
                  <p className="truncate text-[11px] text-ink-subtle">{po.category}</p>
                </td>
                <td className="px-3 py-2">
                  <PurchaseOrderBadge status={po.order_status} />
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-ink-muted">{formatShortDate(po.order_date)}</td>
                <td className="whitespace-nowrap px-3 py-2 text-ink-muted">{formatShortDate(po.expected_delivery_date)}</td>
                <td className={cn("whitespace-nowrap px-3 py-2", late.tone)}>{late.text}</td>
                <td className="px-3 py-2 text-right tabular-nums text-ink-muted">{formatInteger(po.quantity_ordered)}</td>
                <td className="py-2 pl-3 text-right tabular-nums text-ink">{formatCurrency(po.value)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

interface SupplierOrdersCardProps {
  overdue: PurchaseOrder[];
  recent: PurchaseOrder[];
  totalOrders: number;
  links: ReturnType<typeof supplierLinks>;
}

/** Overdue orders (most overdue first) and the most recently placed orders, linking to the full list. */
export function SupplierOrdersCard({ overdue, recent, totalOrders, links }: SupplierOrdersCardProps) {
  const link = "inline-flex items-center gap-1 text-xs font-medium text-brand hover:text-brand-strong";
  return (
    <Card
      title="Purchase orders"
      description={`${formatInteger(totalOrders)} orders in the data`}
      action={
        <Link href={links.orders} className={link}>
          View all in Purchase Orders <ArrowUpRight aria-hidden className="size-3.5" />
        </Link>
      }
    >
      <div className="space-y-6">
        {overdue.length > 0 && (
          <section aria-labelledby="supplier-overdue-title">
            <div className="mb-2 flex items-baseline justify-between gap-3">
              <h3 id="supplier-overdue-title" className="text-[13px] font-semibold text-red-700">
                Overdue ({formatInteger(overdue.length)})
              </h3>
              <Link href={links.overdueOrders} className={link}>
                Open in Purchase Orders <ArrowUpRight aria-hidden className="size-3.5" />
              </Link>
            </div>
            <OrderTable caption="Overdue orders, most overdue first" orders={overdue} />
          </section>
        )}
        <section aria-labelledby="supplier-recent-title">
          <h3 id="supplier-recent-title" className="mb-2 text-[13px] font-semibold text-ink">
            Most recent orders
          </h3>
          <OrderTable caption="The most recently placed orders" orders={recent} />
        </section>
      </div>
    </Card>
  );
}
