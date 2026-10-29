"use client";

import { ArrowDown, ArrowUp, ArrowUpDown, ArrowUpRight, ChevronRight, ClipboardCheck, TriangleAlert } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { Fragment, useState, type ReactNode } from "react";

import { InventoryPagination } from "@/components/inventory/inventory-pagination";
import { cardClassName, fadeUp } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { StockMeter } from "@/components/ui/stock-meter";
import { cn } from "@/lib/cn";
import { formatCurrency, formatInteger, formatPercent, formatShortDate, formatStore } from "@/lib/format";
import { positionLinks, type ReplenishmentQuery, type SortField } from "@/lib/replenishment/query";
import type { Recommendation, RecommendationPage } from "@/lib/replenishment/types";

import { ActionLabel, PriorityBadge } from "./priority-badge";

const CONFIDENCE = { high: "high confidence", medium: "medium confidence", low: "low confidence" } as const;

/** The next open delivery and, for expedite rows, why it is a problem. */
function delivery(row: Recommendation): { text: string; tone: string } | null {
  if (!row.next_delivery) return null;
  const due = `due ${formatShortDate(row.next_delivery)}`;
  if (row.next_delivery_overdue) return { text: `${due}, overdue`, tone: "font-medium text-red-700" };
  if (row.action === "expedite") {
    // Expedited either because it lands after the projected run-out, or because it was due on the
    // as-of date and had not arrived by the end-of-day snapshot.
    return { text: row.days_without_stock ? `${due}, after run-out` : `${due}, not arrived`, tone: "font-medium text-red-700" };
  }
  return { text: due, tone: "text-ink-muted" };
}

interface RecommendationsTableProps {
  page: RecommendationPage;
  query: ReplenishmentQuery;
  onSort: (field: SortField) => void;
  onPage: (page: number) => void;
  onPageSize: (pageSize: number) => void;
  onClear: () => void;
}

export function RecommendationsTable({ page, query, onSort, onPage, onPageSize, onClear }: RecommendationsTableProps) {
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const toggle = (id: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const secondary = "rounded-lg border border-line bg-white px-3 py-1.5 text-sm font-medium text-ink shadow-sm hover:border-line-strong";

  return (
    <motion.section variants={fadeUp} aria-labelledby="recommendations-title" className={cn(cardClassName, "overflow-hidden")}>
      <div className="p-4 sm:p-5">
        <h2 id="recommendations-title" className="text-[15px] font-semibold tracking-tight text-ink">
          Recommendations
        </h2>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          One row per store and product, most urgent first. Open a row to see why, step by step. Demand and run-out dates are estimates.
        </p>
      </div>

      {page.total === 0 ? (
        <EmptyState
          icon={ClipboardCheck}
          title="Nothing needs attention for these filters"
          description="Try another view (Watch or All), a different store, category or supplier, or clear the search."
          action={
            <button type="button" onClick={onClear} className={secondary}>
              Clear filters
            </button>
          }
          className="border-t border-line py-14"
        />
      ) : page.items.length === 0 ? (
        <EmptyState
          icon={ClipboardCheck}
          title={`Page ${page.page} is past the end`}
          description={`There are ${page.total_pages} pages for these filters.`}
          action={
            <button type="button" onClick={() => onPage(page.total_pages)} className={secondary}>
              Go to last page
            </button>
          }
          className="border-t border-line py-14"
        />
      ) : (
        <>
          <DesktopTable rows={page.items} query={query} onSort={onSort} open={open} onToggle={toggle} />
          <MobileList rows={page.items} open={open} onToggle={toggle} />
        </>
      )}

      {page.total > 0 && (
        <div className="border-t border-line px-4 py-3 sm:px-5">
          <InventoryPagination
            page={query.page}
            pageSize={query.pageSize}
            total={page.total}
            totalPages={page.total_pages}
            onPage={onPage}
            onPageSize={onPageSize}
          />
        </div>
      )}
    </motion.section>
  );
}

function SortHeader({ field, children, align, query, onSort }: { field: SortField; children: ReactNode; align?: "right"; query: ReplenishmentQuery; onSort: (f: SortField) => void }) {
  const active = query.sort === field;
  const Icon = !active ? ArrowUpDown : query.order === "asc" ? ArrowUp : ArrowDown;
  return (
    <th scope="col" aria-sort={active ? (query.order === "asc" ? "ascending" : "descending") : "none"} className={cn("px-3 py-2 font-medium", align === "right" && "text-right")}>
      <button
        type="button"
        onClick={() => onSort(field)}
        className={cn("inline-flex items-center gap-1 rounded uppercase tracking-wide hover:text-ink", active && "text-ink", align === "right" && "flex-row-reverse")}
      >
        {children}
        <Icon aria-hidden className={cn("size-3", !active && "opacity-40")} />
      </button>
    </th>
  );
}

interface ListProps {
  rows: Recommendation[];
  open: Set<string>;
  onToggle: (id: string) => void;
}

function DesktopTable({ rows, query, onSort, open, onToggle }: ListProps & { query: ReplenishmentQuery; onSort: (f: SortField) => void }) {
  const header = { query, onSort };
  return (
    <div className="hidden overflow-x-auto md:block">
      <table className="w-full min-w-[1040px] text-left text-[13px]">
        <caption className="sr-only">Replenishment recommendations. Column headers sort the table; open a row for the calculation.</caption>
        <thead>
          <tr className="border-y border-line bg-slate-50/60 text-[11px] text-ink-subtle">
            <th scope="col" className="w-10 px-3 py-2">
              <span className="sr-only">Details</span>
            </th>
            <SortHeader field="product_name" {...header}>Product</SortHeader>
            <SortHeader field="priority" {...header}>Priority</SortHeader>
            <th scope="col" className="px-3 py-2 text-right font-medium uppercase tracking-wide">Stock</th>
            <SortHeader field="run_out_date" {...header}>Demand · run-out</SortHeader>
            <th scope="col" className="px-3 py-2 font-medium uppercase tracking-wide">On order</th>
            <SortHeader field="supplier_name" {...header}>Supplier</SortHeader>
            <SortHeader field="quantity" align="right" {...header}>Recommend</SortHeader>
            <SortHeader field="order_cost" align="right" {...header}>Cost</SortHeader>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isOpen = open.has(row.position_id);
            const detailId = `why-${row.position_id}`;
            const incoming = delivery(row);
            return (
              <Fragment key={row.position_id}>
                <tr className={cn("border-b border-line align-top transition-colors hover:bg-slate-50/70", isOpen && "bg-slate-50/70")}>
                  <td className="px-3 py-2.5">
                    <button
                      type="button"
                      onClick={() => onToggle(row.position_id)}
                      aria-expanded={isOpen}
                      aria-controls={detailId}
                      aria-label={`Why: ${row.product_name} at ${formatStore(row.store_id)}`}
                      className="grid size-7 place-items-center rounded-md text-ink-subtle hover:bg-slate-200/60 hover:text-ink"
                    >
                      <ChevronRight aria-hidden className={cn("size-4 transition-transform", isOpen && "rotate-90")} />
                    </button>
                  </td>
                  <td className="max-w-[200px] px-3 py-2.5">
                    <p className="truncate font-medium text-ink">{row.product_name}</p>
                    <p className="truncate text-xs text-ink-subtle">
                      {row.sku} · {formatStore(row.store_id)}
                    </p>
                  </td>
                  <td className="px-3 py-2.5">
                    <PriorityBadge priority={row.priority} />
                    <ActionLabel action={row.action} className="mt-1 flex" />
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <p className="font-semibold tabular-nums text-ink">{formatInteger(row.available)}</p>
                    <StockMeter available={row.available} reorderPoint={row.reorder_point} safetyStock={row.safety_stock} status={row.stock_status} className="ml-auto mt-1 w-16" />
                    <p className="mt-0.5 text-[11px] tabular-nums text-ink-subtle">
                      safety {row.safety_stock} · reorder {row.reorder_point}
                    </p>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5">
                    <p className="tabular-nums text-ink" title={`Estimated from ${row.demand_basis}, ${CONFIDENCE[row.demand_confidence]}`}>
                      {row.demand_per_day.toFixed(2)}/day <span className="text-[11px] text-ink-subtle">est.</span>
                      {row.demand_confidence !== "high" && (
                        <span className={cn("ml-1 text-[11px] font-medium", row.demand_confidence === "low" ? "text-amber-700" : "text-ink-muted")}>
                          {row.demand_confidence}
                        </span>
                      )}
                    </p>
                    <p className="text-[11px] tabular-nums text-ink-subtle">
                      {row.run_out_date ? `out ${formatShortDate(row.run_out_date)} · ${row.days_of_cover?.toFixed(1)}d cover` : "no projected run-out"}
                    </p>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5">
                    <p className="tabular-nums text-ink">{row.on_order ? `${formatInteger(row.on_order)} units` : "—"}</p>
                    {incoming && <p className={cn("text-[11px]", incoming.tone)}>{incoming.text}</p>}
                    {row.days_without_stock ? (
                      <p className="text-[11px] text-red-700" title="Projected days without stock: an estimate">
                        ~{row.days_without_stock}d without stock (est.)
                      </p>
                    ) : null}
                  </td>
                  <td className="max-w-[180px] px-3 py-2.5">
                    <Link href={positionLinks(row).supplier} className="block truncate text-ink hover:text-brand">
                      {row.supplier_name}
                    </Link>
                    <p className="truncate text-[11px] tabular-nums text-ink-subtle">
                      lead {row.stated_lead_time_days}d stated
                      {row.observed_lead_time_days !== null && ` · ${row.observed_lead_time_days.toFixed(1)}d obs.`}
                    </p>
                    <p className="text-[11px] tabular-nums text-ink-subtle">min order {row.minimum_order_quantity}</p>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-right">
                    {row.quantity ? (
                      <>
                        <p className="font-semibold tabular-nums text-ink">{formatInteger(row.quantity)}</p>
                        {row.raised_to_moq && <p className="text-[11px] font-medium text-sky-700">raised to minimum</p>}
                        {row.exceeds_shelf_life && (
                          <p className="inline-flex items-center gap-0.5 text-[11px] font-semibold text-amber-700">
                            <TriangleAlert aria-hidden className="size-3" /> shelf life
                          </p>
                        )}
                      </>
                    ) : (
                      <p className="text-[11px] text-ink-subtle">{row.action === "order" ? "review manually" : "no new order"}</p>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums text-ink">{row.quantity ? formatCurrency(row.order_cost) : "—"}</td>
                </tr>
                {isOpen && (
                  <tr id={detailId} className="border-b border-line bg-slate-50/70">
                    <td />
                    <td colSpan={8} className="px-3 pb-4 pt-1">
                      <Why row={row} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function MobileList({ rows, open, onToggle }: ListProps) {
  return (
    <ul className="divide-y divide-line border-t border-line md:hidden">
      {rows.map((row) => {
        const isOpen = open.has(row.position_id);
        return (
          <li key={row.position_id} className="px-4 py-3.5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-ink">{row.product_name}</p>
                <p className="truncate text-xs text-ink-subtle">
                  {formatStore(row.store_id)} · {row.supplier_name}
                </p>
              </div>
              <div className="text-right">
                <PriorityBadge priority={row.priority} />
                <ActionLabel action={row.action} className="mt-1 flex justify-end" />
              </div>
            </div>
            <dl className="mt-3 grid grid-cols-3 gap-x-3 gap-y-2">
              {(
                [
                  ["Available", `${formatInteger(row.available)} / ${row.reorder_point}`],
                  ["Demand (est.)", `${row.demand_per_day.toFixed(2)}/day`],
                  ["Run-out", row.run_out_date ? formatShortDate(row.run_out_date) : "—"],
                  ["On order", row.on_order ? formatInteger(row.on_order) : "—"],
                  ["Recommend", row.quantity ? formatInteger(row.quantity) : "—"],
                  ["Cost", row.quantity ? formatCurrency(row.order_cost) : "—"],
                ] as const
              ).map(([label, value]) => (
                <div key={label} className="min-w-0">
                  <dt className="truncate text-[11px] text-ink-subtle">{label}</dt>
                  <dd className="truncate text-[13px] font-medium tabular-nums text-ink">{value}</dd>
                </div>
              ))}
            </dl>
            {row.exceeds_shelf_life && (
              <p className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-amber-700">
                <TriangleAlert aria-hidden className="size-3.5" /> Exceeds shelf life
              </p>
            )}
            <button
              type="button"
              onClick={() => onToggle(row.position_id)}
              aria-expanded={isOpen}
              className="mt-2 flex items-center gap-1 text-xs font-medium text-brand hover:text-brand-strong"
            >
              {isOpen ? "Hide" : "Why?"}
              <ChevronRight aria-hidden className={cn("size-3.5 transition-transform", isOpen && "rotate-90")} />
            </button>
            {isOpen && (
              <div className="mt-3">
                <Why row={row} />
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** The reasons, warnings and calculation steps for one row, with links to the related pages. */
function Why({ row }: { row: Recommendation }) {
  const links = positionLinks(row);
  const link = "inline-flex items-center gap-0.5 text-xs font-medium text-brand hover:text-brand-strong";
  return (
    <div className="space-y-3 rounded-xl border border-line bg-white p-3 text-[13px]">
      <div className="space-y-1">
        <p>
          <span className="font-semibold text-ink">Priority:</span> <span className="text-ink-muted">{row.priority_reason}</span>
        </p>
        <p>
          <span className="font-semibold text-ink">Action:</span> <span className="text-ink-muted">{row.action_reason}</span>
        </p>
      </div>
      {row.warnings.length > 0 && (
        <ul className="space-y-1">
          {row.warnings.map((warning) => (
            <li key={warning} className="flex items-start gap-1.5 rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs text-amber-950 ring-1 ring-inset ring-amber-600/20">
              <TriangleAlert aria-hidden className="mt-px size-3.5 shrink-0 text-amber-700" />
              {warning}
            </li>
          ))}
        </ul>
      )}
      <div>
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-subtle">How it&apos;s calculated</p>
        <ol className="list-decimal space-y-0.5 pl-5 text-xs leading-5 text-ink-muted">
          {row.explanation.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </div>
      <p className="text-[11px] text-ink-subtle">
        Supplier on-time rate {row.supplier_on_time_rate === null ? "—" : formatPercent(row.supplier_on_time_rate)} (observed) · stock{" "}
        {formatInteger(row.on_hand)} on hand, {formatInteger(row.reserved)} reserved
      </p>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        <Link href={links.stock} className={link}>
          Stock position <ArrowUpRight aria-hidden className="size-3.5" />
        </Link>
        <Link href={links.orders} className={link}>
          Orders for this product <ArrowUpRight aria-hidden className="size-3.5" />
        </Link>
        <Link href={links.supplier} className={link}>
          {row.supplier_name} <ArrowUpRight aria-hidden className="size-3.5" />
        </Link>
      </div>
    </div>
  );
}
