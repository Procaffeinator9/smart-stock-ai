"use client";

import { ArrowDown, ArrowUp, ArrowUpDown, ChevronRight, Truck } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import type { ReactNode } from "react";

import { Select } from "@/components/inventory/inventory-filters";
import { cardClassName, fadeUp } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/cn";
import { formatCurrencyCompact, formatInteger, formatPercent } from "@/lib/format";
import { supplierLinks, type ScoreSortField, type SupplierQuery } from "@/lib/suppliers/query";
import type { SupplierScore } from "@/lib/suppliers/types";

import { FlagChips } from "./flag-chips";
import { leadTimeText, rateOrDash } from "./supplier-format";

const SORT_LABELS: Record<ScoreSortField, string> = {
  attention: "Attention flags",
  supplier_name: "Supplier",
  on_time_rate: "On-time rate",
  reliability_gap: "Observed − stated reliability",
  stated_reliability: "Stated reliability",
  lead_time_gap_days: "Lead-time gap",
  spend: "Spend",
  orders: "Orders",
  overdue_orders: "Overdue orders",
  at_risk_positions: "At-risk positions",
  revenue: "Revenue",
  stockout_days: "Stockout days",
};

interface ScorecardTableProps {
  rows: SupplierScore[];
  query: SupplierQuery;
  onSort: (field: ScoreSortField) => void;
  onClear: () => void;
}

export function ScorecardTable({ rows, query, onSort, onClear }: ScorecardTableProps) {
  return (
    <motion.section variants={fadeUp} aria-labelledby="scorecard-title" className={cn(cardClassName, "overflow-hidden")}>
      <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-end sm:justify-between sm:p-5">
        <div>
          <h2 id="scorecard-title" className="text-[15px] font-semibold tracking-tight text-ink">
            Supplier scorecard
          </h2>
          <p className="mt-0.5 text-[13px] text-ink-muted">
            Observed on-time rate next to the supplier&apos;s stated reliability, and observed lead time next to the stated one. Hover a
            flag for its reason.
          </p>
        </div>
        <div className="md:hidden">
          <Select label="Sort suppliers by" value={query.sort} onChange={(value) => onSort(value as ScoreSortField)}>
            {Object.entries(SORT_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                Sort: {label}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {rows.length === 0 ? (
        <EmptyState
          icon={Truck}
          title="No suppliers match"
          description="Try a different search term or attention filter."
          action={
            <button
              type="button"
              onClick={onClear}
              className="rounded-lg border border-line bg-white px-3 py-1.5 text-sm font-medium text-ink shadow-sm hover:border-line-strong"
            >
              Clear filters
            </button>
          }
          className="border-t border-line py-14"
        />
      ) : (
        <>
          <DesktopTable rows={rows} query={query} onSort={onSort} />
          <MobileList rows={rows} />
        </>
      )}
    </motion.section>
  );
}

function SortHeader({ field, children, align, query, onSort }: { field: ScoreSortField; children: ReactNode; align?: "right"; query: SupplierQuery; onSort: (field: ScoreSortField) => void }) {
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

function DesktopTable({ rows, query, onSort }: { rows: SupplierScore[]; query: SupplierQuery; onSort: (field: ScoreSortField) => void }) {
  const header = { query, onSort };
  return (
    <div className="hidden overflow-x-auto md:block">
      <table className="w-full min-w-[1080px] text-left text-[13px]">
        <caption className="sr-only">Supplier scorecard. Column headers sort the table; supplier names open the supplier&apos;s page.</caption>
        <thead>
          <tr className="border-y border-line bg-slate-50/60 text-[11px] text-ink-subtle">
            <SortHeader field="supplier_name" {...header}>Supplier</SortHeader>
            <SortHeader field="attention" {...header}>Attention</SortHeader>
            <SortHeader field="on_time_rate" align="right" {...header}>On time</SortHeader>
            <SortHeader field="lead_time_gap_days" align="right" {...header}>Lead time</SortHeader>
            <SortHeader field="spend" align="right" {...header}>Spend</SortHeader>
            <SortHeader field="overdue_orders" align="right" {...header}>Overdue</SortHeader>
            <SortHeader field="at_risk_positions" align="right" {...header}>At-risk stock</SortHeader>
            <SortHeader field="revenue" align="right" {...header}>Revenue</SortHeader>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const lead = leadTimeText(row);
            return (
              <tr key={row.supplier_id} className="border-b border-line align-top transition-colors last:border-b-0 hover:bg-slate-50/70">
                <td className="px-3 py-2.5">
                  <Link href={supplierLinks(row.supplier_id, row.supplier_name).detail} className="group inline-flex items-center gap-1 font-medium text-ink hover:text-brand">
                    {row.supplier_name}
                    <ChevronRight aria-hidden className="size-3.5 text-ink-subtle group-hover:text-brand" />
                  </Link>
                  <p className="text-xs text-ink-subtle">
                    {row.supplier_id} · {formatInteger(row.products)} products
                  </p>
                </td>
                <td className="max-w-[260px] px-3 py-2.5">
                  <FlagChips flags={row.flags} />
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 text-right">
                  <p className={cn("font-semibold tabular-nums", row.flags.some((f) => f.code === "low_on_time") ? "text-red-700" : "text-ink")}>
                    {rateOrDash(row.on_time_rate)}
                  </p>
                  <p className="text-[11px] tabular-nums text-ink-subtle">
                    of {formatInteger(row.sample_size)} · stated {formatPercent(row.stated_reliability)}
                  </p>
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 text-right">
                  <p className="tabular-nums text-ink">{lead.observed}</p>
                  <p className={cn("text-[11px] tabular-nums", lead.slipping ? "font-medium text-amber-700" : "text-ink-subtle")}>{lead.detail}</p>
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 text-right">
                  <p className="tabular-nums text-ink">{formatCurrencyCompact(row.spend)}</p>
                  <p className="text-[11px] tabular-nums text-ink-subtle">{formatInteger(row.orders)} orders</p>
                </td>
                <td className={cn("px-3 py-2.5 text-right tabular-nums", row.overdue_orders ? "font-semibold text-red-700" : "text-ink-subtle")}>
                  {row.overdue_orders ? formatInteger(row.overdue_orders) : "—"}
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 text-right">
                  <p className={cn("tabular-nums", row.at_risk_positions ? "font-medium text-ink" : "text-ink-subtle")}>
                    {formatInteger(row.at_risk_positions)} of {formatInteger(row.positions)}
                  </p>
                  <p className="text-[11px] tabular-nums text-ink-subtle">{formatInteger(row.stockout_days)} stockout days</p>
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 text-right">
                  <p className="tabular-nums text-ink">{formatCurrencyCompact(row.revenue)}</p>
                  <p className="text-[11px] tabular-nums text-ink-subtle">{row.revenue_share === null ? "—" : `${formatPercent(row.revenue_share)} of total`}</p>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function MobileList({ rows }: { rows: SupplierScore[] }) {
  return (
    <ul className="divide-y divide-line border-t border-line md:hidden">
      {rows.map((row) => {
        const lead = leadTimeText(row);
        return (
          <li key={row.supplier_id} className="px-4 py-3.5">
            <Link href={supplierLinks(row.supplier_id, row.supplier_name).detail} className="flex items-start justify-between gap-3">
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-ink">{row.supplier_name}</span>
                <span className="block truncate text-xs text-ink-subtle">
                  {row.supplier_id} · {formatInteger(row.products)} products
                </span>
              </span>
              <ChevronRight aria-hidden className="mt-0.5 size-4 shrink-0 text-ink-subtle" />
            </Link>
            <FlagChips flags={row.flags} className="mt-2" />
            <dl className="mt-3 grid grid-cols-3 gap-x-3 gap-y-2">
              {(
                [
                  ["On time", `${rateOrDash(row.on_time_rate)} of ${formatInteger(row.sample_size)}`],
                  ["Stated", formatPercent(row.stated_reliability)],
                  ["Lead time", lead.observed],
                  ["Spend", formatCurrencyCompact(row.spend)],
                  ["Overdue", formatInteger(row.overdue_orders)],
                  ["At-risk stock", `${formatInteger(row.at_risk_positions)} of ${formatInteger(row.positions)}`],
                ] as const
              ).map(([label, value]) => (
                <div key={label} className="min-w-0">
                  <dt className="truncate text-[11px] text-ink-subtle">{label}</dt>
                  <dd className="truncate text-[13px] font-medium tabular-nums text-ink">{value}</dd>
                </div>
              ))}
            </dl>
          </li>
        );
      })}
    </ul>
  );
}
