"use client";

import { ClipboardList, Download, FlaskConical, RotateCcw, TriangleAlert } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useState } from "react";

import { cardClassName, fadeUp } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/cn";
import { formatCurrency, formatInteger, formatShortDate, formatStore } from "@/lib/format";
import { planCsv, planFileName, planTotals } from "@/lib/replenishment/plan";
import type { ReplenishmentPlan } from "@/lib/replenishment/types";

import { PriorityBadge } from "./priority-badge";

/**
 * The simulated reorder plan: every recommended order line, grouped by supplier. Users can leave
 * lines out and download the rest as CSV. Everything happens in the browser: there are no quantity
 * edits, nothing is sent to the server, and no purchase order is created.
 */
export function ReorderPlanCard({ plan }: { plan: ReplenishmentPlan }) {
  const [excluded, setExcluded] = useState<Set<string>>(() => new Set());
  const { plan: p } = plan;
  const totals = planTotals(p, excluded);

  const setIncluded = (ids: string[], include: boolean) =>
    setExcluded((current) => {
      const next = new Set(current);
      for (const id of ids) {
        if (include) next.delete(id);
        else next.add(id);
      }
      return next;
    });

  function download() {
    const blob = new Blob([planCsv(p, excluded)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = planFileName(plan.as_of);
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  const button = "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium shadow-sm disabled:opacity-50";

  return (
    <motion.section variants={fadeUp} id="reorder-plan" aria-labelledby="reorder-plan-title" className={cn(cardClassName, "scroll-mt-24 overflow-hidden")}>
      <div className="flex flex-wrap items-start justify-between gap-3 p-4 sm:p-5">
        <div className="min-w-0">
          <h2 id="reorder-plan-title" className="text-[15px] font-semibold tracking-tight text-ink">
            Simulated reorder plan
          </h2>
          <p className="mt-0.5 text-[13px] text-ink-muted">
            Every recommended order for the current store, category, supplier and search filters, grouped by supplier. Leave lines out to
            see the totals change.
          </p>
        </div>
        <p className="inline-flex items-center gap-1.5 rounded-full bg-violet-50 px-2.5 py-1 text-xs font-semibold text-violet-800 ring-1 ring-inset ring-violet-600/20">
          <FlaskConical aria-hidden className="size-3.5" /> Simulation: no purchase orders are created
        </p>
      </div>

      {p.lines === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title="No orders to recommend for these filters"
          description={
            p.manual_review
              ? `${p.manual_review} position(s) need an order but have no recent demand; review them manually in the table.`
              : "Stock plus open orders is above the reorder point everywhere in this selection."
          }
          className="border-t border-line py-12"
        />
      ) : (
        <>
          {totals.shelfLifeWarnings > 0 && (
            <p role="status" className="mx-4 mb-3 flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-[13px] text-amber-950 ring-1 ring-inset ring-amber-600/20 sm:mx-5">
              <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-amber-700" />
              <span>
                <span className="font-semibold">
                  {formatInteger(totals.shelfLifeWarnings)} included {totals.shelfLifeWarnings === 1 ? "line exceeds" : "lines exceed"} shelf life.
                </span>{" "}
                The stock after ordering would outlast the product. Quantities are not capped; consider leaving these lines out or ordering less
                outside this tool.
              </span>
            </p>
          )}

          <div className="divide-y divide-line border-t border-line">
            {p.suppliers.map((group) => {
              const groupTotals = totals.bySupplier[group.supplier_id];
              const ids = group.items.map((i) => i.position_id);
              const allIncluded = ids.every((id) => !excluded.has(id));
              return (
                <section key={group.supplier_id} aria-label={`Order lines for ${group.supplier_name}`} className="px-4 py-3 sm:px-5">
                  <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                    <div className="min-w-0">
                      <Link href={`/suppliers/${encodeURIComponent(group.supplier_id)}`} className="font-medium text-ink hover:text-brand">
                        {group.supplier_name}
                      </Link>
                      <span className="ml-2 text-xs text-ink-subtle">
                        stated lead {group.stated_lead_time_days} days
                        {group.expected_arrival && ` · arrives about ${formatShortDate(group.expected_arrival)} if ordered on ${formatShortDate(plan.as_of)}`}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs">
                      <span className="tabular-nums text-ink-muted">
                        {groupTotals.lines} of {group.lines} lines · {formatInteger(groupTotals.units)} units ·{" "}
                        <span className="font-semibold text-ink">{formatCurrency(groupTotals.cost)}</span>
                      </span>
                      <button
                        type="button"
                        onClick={() => setIncluded(ids, !allIncluded)}
                        className="font-medium text-brand hover:text-brand-strong"
                      >
                        {allIncluded ? "Leave all out" : "Include all"}
                      </button>
                    </div>
                  </div>
                  <ul className="space-y-1">
                    {group.items.map((item) => {
                      const included = !excluded.has(item.position_id);
                      const inputId = `plan-${item.position_id}`;
                      return (
                        <li
                          key={item.position_id}
                          className={cn(
                            "grid grid-cols-[auto_minmax(0,1fr)] items-start gap-x-3 gap-y-1 rounded-lg px-2 py-1.5 sm:grid-cols-[auto_minmax(0,1fr)_auto_7rem_6rem]",
                            !included && "opacity-50",
                          )}
                        >
                          <input
                            id={inputId}
                            type="checkbox"
                            checked={included}
                            onChange={(event) => setIncluded([item.position_id], event.target.checked)}
                            className="mt-1 size-4 rounded border-line-strong accent-brand"
                          />
                          <label htmlFor={inputId} className="min-w-0 cursor-pointer">
                            <span className="block truncate text-[13px] font-medium text-ink">{item.product_name}</span>
                            <span className="block truncate text-xs text-ink-subtle">
                              {item.sku} · {formatStore(item.store_id)}
                            </span>
                            {item.exceeds_shelf_life && (
                              <span className="mt-0.5 flex items-center gap-1 text-xs font-semibold text-amber-700">
                                <TriangleAlert aria-hidden className="size-3.5" />
                                Exceeds shelf life: lasts ~{item.stock_days_after_order?.toFixed(1)} days, keeps {item.shelf_life_days}
                              </span>
                            )}
                          </label>
                          <span className="col-start-2 sm:col-start-auto">
                            <PriorityBadge priority={item.priority} />
                          </span>
                          <span className="col-start-2 text-[13px] tabular-nums text-ink sm:col-start-auto sm:text-right">
                            {formatInteger(item.quantity)} units
                            {item.raised_to_moq && <span className="block text-[11px] font-medium text-sky-700">minimum order</span>}
                          </span>
                          <span className="col-start-2 text-[13px] font-medium tabular-nums text-ink sm:col-start-auto sm:text-right">
                            {formatCurrency(item.order_cost)}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              );
            })}
          </div>

          <div className="flex flex-col gap-3 border-t border-line bg-slate-50/60 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <p className="text-[13px] text-ink-muted" aria-live="polite">
              Included: <span className="font-semibold tabular-nums text-ink">{formatInteger(totals.lines)}</span> of {formatInteger(p.lines)} lines ·{" "}
              <span className="font-semibold tabular-nums text-ink">{formatInteger(totals.units)}</span> units · estimated{" "}
              <span className="font-semibold tabular-nums text-ink">{formatCurrency(totals.cost)}</span>
              {p.manual_review > 0 && <> · {formatInteger(p.manual_review)} more need manual review</>}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setExcluded(new Set())}
                disabled={excluded.size === 0}
                className={cn(button, "border border-line bg-white text-ink hover:border-line-strong")}
              >
                <RotateCcw aria-hidden className="size-4" /> Include all
              </button>
              <button type="button" onClick={download} disabled={totals.lines === 0} className={cn(button, "bg-brand text-white hover:bg-brand-strong")}>
                <Download aria-hidden className="size-4" /> Download CSV
              </button>
            </div>
          </div>
        </>
      )}
    </motion.section>
  );
}
