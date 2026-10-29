"use client";

import { BadgePercent } from "lucide-react";

import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { formatCurrencyCompact, formatInteger, formatPercent } from "@/lib/format";
import type { PromotionMetrics } from "@/lib/sales/types";

interface PromotionCardProps {
  promotion: PromotionMetrics;
  /** The page's promotion filter: true = promotional sales only, false = regular-price only. */
  filter: boolean | null;
  className?: string;
}

const percentOrDash = (value: number | null) => (value === null ? "—" : formatPercent(value));

export function PromotionCard({ promotion, filter, className }: PromotionCardProps) {
  const share = promotion.revenue_share ?? 0;
  const uplift = promotion.uplift;
  const facts: Array<[string, string, string]> = [
    ["Revenue on promotion", formatCurrencyCompact(promotion.promo_revenue), `${percentOrDash(promotion.revenue_share)} of revenue`],
    ["Units on promotion", formatInteger(promotion.promo_units), `${percentOrDash(promotion.units_share)} of units`],
    ["Average discount", percentOrDash(promotion.avg_discount), "off list price, weighted by units"],
    ["Promoted products", formatInteger(promotion.promoted_products), `${formatInteger(promotion.promo_lines)} store-days with promotional sales`],
  ];

  return (
    <Card title="Promotions" description="Promotional sales in this period" className={className}>
      {filter === false ? (
        <EmptyState
          icon={BadgePercent}
          title="Showing regular-price sales only"
          description="Choose “All sales” to compare promotional and regular-price sales."
        />
      ) : promotion.promo_lines === 0 ? (
        <EmptyState icon={BadgePercent} title="No promotional sales" description="No product was sold on promotion with these filters." />
      ) : (
        <div className="space-y-4">
          {filter === null && (
            <div>
              <div className="mb-1.5 flex justify-between text-xs text-ink-subtle">
                <span>On promotion {formatPercent(share)}</span>
                <span>Regular price {formatPercent(1 - share)}</span>
              </div>
              <div className="flex h-2 overflow-hidden rounded-full bg-slate-100" role="img" aria-label={`${formatPercent(share)} of revenue was on promotion`}>
                <span className="h-full bg-violet-500" style={{ width: `${share * 100}%` }} />
              </div>
            </div>
          )}
          <dl className="grid grid-cols-2 gap-2">
            {facts.map(([label, value, note]) => (
              <div key={label} className="rounded-lg bg-slate-50 px-3 py-2 ring-1 ring-inset ring-line/70">
                <dt className="text-[11px] text-ink-subtle">{label}</dt>
                <dd className="text-sm font-semibold tabular-nums text-ink">{value}</dd>
                <dd className="text-[11px] leading-4 text-ink-subtle">{note}</dd>
              </div>
            ))}
          </dl>
          <div className="rounded-lg border border-violet-200/70 bg-violet-50/60 px-3 py-2.5 text-xs leading-5 text-violet-950">
            {uplift === null ? (
              <>Uplift needs both promotional and regular-price sales of the same products; choose “All sales” to see it.</>
            ) : (
              <>
                <span className="font-semibold">Measured uplift {uplift >= 0 ? "+" : "−"}{formatPercent(Math.abs(uplift))}</span>: promoted
                products sold {promotion.units_per_line_promo?.toFixed(1)} units per store-day on promotion vs{" "}
                {promotion.units_per_line_regular?.toFixed(1)} at the regular price (days with at least one sale).
              </>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
