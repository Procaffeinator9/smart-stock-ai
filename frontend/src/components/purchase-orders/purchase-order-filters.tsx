"use client";

import { CalendarRange, X } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";

import { Select } from "@/components/inventory/inventory-filters";
import { CustomRange } from "@/components/sales/sales-filters";
import { cardClassName, fadeUp } from "@/components/ui/card";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { PO_STATUS } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import type { PurchaseOrderStatus } from "@/lib/dashboard/types";
import { formatDateRange, formatInteger, formatLongDate, formatStore } from "@/lib/format";
import {
  isCustomRange,
  PO_STATUSES,
  RANGE_PRESETS,
  type LatenessFilter,
  type PurchaseOrderQuery,
  type RangePreset,
} from "@/lib/purchase-orders/query";
import type { PurchaseOrderSummary } from "@/lib/purchase-orders/types";

type RangeChoice = "all" | `${RangePreset}` | "custom";

const RANGE_OPTIONS: Array<{ value: RangeChoice; label: string; title?: string }> = [
  { value: "all", label: "All", title: "Every order date in the data" },
  ...[...RANGE_PRESETS].reverse().map((days) => ({
    value: `${days}` as RangeChoice,
    label: `${days}D`,
    title: `Orders placed in the last ${days} days of data`,
  })),
  { value: "custom", label: "Custom", title: "Choose order dates" },
];

const LATENESS_OPTIONS = [
  { value: "all" as const, label: "All orders" },
  { value: "overdue" as const, label: "Overdue", title: "Open and past the promised date" },
  { value: "late" as const, label: "Delivered late", title: "Delivered after the promised date" },
];

interface PurchaseOrderFiltersProps {
  query: PurchaseOrderQuery;
  summary: PurchaseOrderSummary;
  onChange: (patch: Partial<PurchaseOrderQuery>) => void;
  onClear: () => void;
  active: boolean;
}

export function PurchaseOrderFilters({ query, summary, onChange, onClear, active }: PurchaseOrderFiltersProps) {
  const [customOpen, setCustomOpen] = useState(false);
  const custom = customOpen || isCustomRange(query);
  const { period, bounds, facets, as_of: asOf } = summary;
  const firstDay = bounds.date_from ?? asOf;
  const lastDay = bounds.date_to ?? asOf;
  const counts = new Map(summary.by_status.map((s) => [s.status, s.orders]));
  const value: RangeChoice = custom ? "custom" : query.days === null ? "all" : `${query.days}`;

  function onRange(choice: RangeChoice) {
    if (choice === "custom") {
      setCustomOpen(true);
      return;
    }
    setCustomOpen(false);
    onChange({ days: choice === "all" ? null : (Number(choice) as RangePreset), from: null, to: null });
  }

  function toggleStatus(status: PurchaseOrderStatus) {
    const next = query.status.includes(status) ? query.status.filter((s) => s !== status) : [...query.status, status];
    onChange({ status: PO_STATUSES.filter((s) => next.includes(s)) });
  }

  return (
    <motion.section variants={fadeUp} aria-label="Purchase order filters" className={cn(cardClassName, "space-y-3 p-4 sm:p-5")}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <SegmentedControl label="Order dates" options={RANGE_OPTIONS} value={value} onChange={onRange} />
        {custom && (
          <CustomRange
            key={`${period.date_from}|${period.date_to}`}
            from={period.date_from ?? firstDay}
            to={period.date_to ?? lastDay}
            min={firstDay}
            max={lastDay}
            onApply={(from, to) => onChange({ days: null, from, to })}
          />
        )}
        <p className="flex min-w-0 items-center gap-1.5 text-xs text-ink-muted" aria-live="polite">
          <CalendarRange aria-hidden className="size-3.5 shrink-0 text-ink-subtle" />
          <span>
            Orders placed{" "}
            <span className="font-medium text-ink">
              {formatDateRange(period.date_from ?? firstDay, period.date_to ?? lastDay)}
            </span>{" "}
            · lateness judged as of {formatLongDate(asOf)}
          </span>
        </p>
      </div>

      <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-[11rem_14rem_11rem_auto_auto] lg:items-center">
        <Select label="Store" value={query.store ?? ""} onChange={(v) => onChange({ store: v || null })}>
          <option value="">All stores</option>
          {facets.stores.map((store) => (
            <option key={store} value={store}>
              {formatStore(store)}
            </option>
          ))}
        </Select>
        <Select label="Supplier" value={query.supplier ?? ""} onChange={(v) => onChange({ supplier: v || null })}>
          <option value="">All suppliers</option>
          {facets.suppliers.map((supplier) => (
            <option key={supplier.supplier_id} value={supplier.supplier_id}>
              {supplier.supplier_name}
            </option>
          ))}
        </Select>
        <Select label="Category" value={query.category ?? ""} onChange={(v) => onChange({ category: v || null })}>
          <option value="">All categories</option>
          {facets.categories.map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
          ))}
        </Select>
        <SegmentedControl<LatenessFilter>
          label="Lateness"
          options={LATENESS_OPTIONS}
          value={query.lateness}
          onChange={(lateness) => onChange({ lateness })}
          className="w-fit sm:col-span-3 lg:col-span-1"
        />
        {active && (
          <button
            type="button"
            onClick={onClear}
            className="inline-flex h-9 w-fit items-center gap-1.5 rounded-lg px-3 text-[13px] font-medium text-ink-muted hover:bg-slate-100 hover:text-ink"
          >
            <X aria-hidden className="size-4" /> Clear filters
          </button>
        )}
      </div>

      <div role="group" aria-label="Filter the order table by status" className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          aria-pressed={query.status.length === 0}
          onClick={() => onChange({ status: [] })}
          className={cn(
            "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition-colors",
            query.status.length === 0 ? "border-ink bg-ink text-white" : "border-line bg-white text-ink-muted hover:border-line-strong hover:text-ink",
          )}
        >
          All statuses <span className="tabular-nums opacity-70">{formatInteger(summary.totals.orders)}</span>
        </button>
        {PO_STATUSES.map((status) => {
          const pressed = query.status.includes(status);
          const style = PO_STATUS[status];
          const Icon = style.icon;
          return (
            <button
              key={status}
              type="button"
              aria-pressed={pressed}
              onClick={() => toggleStatus(status)}
              className={cn(
                "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition-colors",
                pressed ? "border-brand/30 bg-brand-soft text-brand-strong" : "border-line bg-white text-ink-muted hover:border-line-strong hover:text-ink",
              )}
            >
              <Icon aria-hidden className="size-3.5" />
              {style.label} <span className="tabular-nums opacity-70">{formatInteger(counts.get(status) ?? 0)}</span>
            </button>
          );
        })}
      </div>
      <p className="text-[11px] text-ink-subtle">
        Store, supplier, category and order dates apply to every figure. Status, lateness and search narrow the order table only.
      </p>
    </motion.section>
  );
}
