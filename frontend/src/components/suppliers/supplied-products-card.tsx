"use client";

import { ArrowUpRight, Package } from "lucide-react";
import Link from "next/link";

import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { formatCurrency, formatDateRange, formatInteger, formatPercent } from "@/lib/format";
import type { SalesPeriod } from "@/lib/sales/types";
import { productStockLink } from "@/lib/suppliers/query";
import type { SuppliedProduct } from "@/lib/suppliers/types";

interface SuppliedProductsCardProps {
  products: SuppliedProduct[];
  revenue: number;
  period: SalesPeriod | null;
}

/** Every product the supplier supplies, most at-risk stock first, with sales over the data period. */
export function SuppliedProductsCard({ products, revenue, period }: SuppliedProductsCardProps) {
  return (
    <Card
      title="Products supplied"
      description={`Stock status on the as-of date, worst first. Revenue and stockout days ${period ? `cover ${formatDateRange(period.date_from, period.date_to)}` : "cover every sale date"}.`}
      bodyClassName="px-0 pb-0"
    >
      {products.length === 0 ? (
        <EmptyState icon={Package} title="This supplier supplies no products" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[880px] text-left text-[13px]">
            <caption className="sr-only">Products supplied, with stock status and sales</caption>
            <thead>
              <tr className="border-y border-line bg-slate-50/60 text-[11px] uppercase tracking-wide text-ink-subtle">
                <th scope="col" className="px-5 py-2 font-medium">Product</th>
                <th scope="col" className="px-3 py-2 font-medium">Stock status</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Available</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">On order</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Revenue</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Units sold</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Stockout days</th>
                <th scope="col" className="px-5 py-2 font-medium">
                  <span className="sr-only">Inventory</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {products.map((p) => (
                <tr key={p.product_id} className="border-b border-line last:border-b-0 hover:bg-slate-50/70">
                  <td className="max-w-[260px] px-5 py-2.5">
                    <p className="truncate font-medium text-ink">{p.product_name}</p>
                    <p className="truncate text-xs text-ink-subtle">
                      {p.sku} · {p.category}
                    </p>
                  </td>
                  <td className="px-3 py-2.5">
                    {p.worst_status ? <StatusBadge status={p.worst_status} /> : <span className="text-ink-subtle">—</span>}
                    <p className={cn("mt-0.5 text-[11px]", p.at_risk_stores ? "font-medium text-red-700" : "text-ink-subtle")}>
                      {p.at_risk_stores ? `${p.at_risk_stores} of ${p.stores} stores at risk` : `${p.stores} stores`}
                    </p>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-ink">{formatInteger(p.available)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-ink-muted">{p.open_po_quantity ? formatInteger(p.open_po_quantity) : "—"}</td>
                  <td className="px-3 py-2.5 text-right">
                    <p className="tabular-nums text-ink">{formatCurrency(p.revenue)}</p>
                    <p className="text-[11px] tabular-nums text-ink-subtle">{revenue ? `${formatPercent(p.revenue / revenue)} of supplier` : "—"}</p>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-ink-muted">{formatInteger(p.units_sold)}</td>
                  <td className={cn("px-3 py-2.5 text-right tabular-nums", p.stockout_days ? "text-ink" : "text-ink-subtle")}>
                    {p.stockout_days ? formatInteger(p.stockout_days) : "—"}
                  </td>
                  <td className="px-5 py-2.5 text-right">
                    <Link
                      href={productStockLink(p.sku)}
                      className="inline-flex items-center gap-0.5 whitespace-nowrap text-xs font-medium text-brand hover:text-brand-strong"
                      aria-label={`Stock positions for ${p.product_name}`}
                    >
                      Stock <ArrowUpRight aria-hidden className="size-3.5" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
