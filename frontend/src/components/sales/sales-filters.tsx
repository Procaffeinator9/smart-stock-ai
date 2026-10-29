"use client";

import { CalendarRange, X } from "lucide-react";
import { motion } from "motion/react";
import { useState, type FormEvent } from "react";

import { Select } from "@/components/inventory/inventory-filters";
import { cardClassName, fadeUp } from "@/components/ui/card";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { cn } from "@/lib/cn";
import { formatDateRange, formatInteger, formatStore } from "@/lib/format";
import { isCustomRange, RANGE_PRESETS, type PromotionFilter, type RangePreset, type SalesQuery } from "@/lib/sales/query";
import type { SalesSummary } from "@/lib/sales/types";

type RangeChoice = `${RangePreset}` | "custom";

const RANGE_OPTIONS = [
  ...RANGE_PRESETS.map((days) => ({ value: `${days}` as RangeChoice, label: `${days}D`, title: `Last ${days} days of data` })),
  { value: "custom" as RangeChoice, label: "Custom", title: "Choose start and end dates" },
];

const PROMOTION_OPTIONS = [
  { value: "all" as const, label: "All sales" },
  { value: "promo" as const, label: "On promotion" },
  { value: "regular" as const, label: "Regular price" },
];

interface SalesFiltersProps {
  query: SalesQuery;
  summary: SalesSummary;
  onChange: (patch: Partial<SalesQuery>) => void;
  onClear: () => void;
  active: boolean;
}

export function SalesFilters({ query, summary, onChange, onClear, active }: SalesFiltersProps) {
  const [customOpen, setCustomOpen] = useState(false);
  const custom = customOpen || isCustomRange(query);
  const { period, previous_period: previous, bounds, facets } = summary;

  function onRange(choice: RangeChoice) {
    if (choice === "custom") {
      setCustomOpen(true);
      return;
    }
    setCustomOpen(false);
    onChange({ days: Number(choice) as RangePreset, from: null, to: null });
  }

  return (
    <motion.section variants={fadeUp} aria-label="Sales filters" className={cn(cardClassName, "space-y-3 p-4 sm:p-5")}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <SegmentedControl label="Date range" options={RANGE_OPTIONS} value={custom ? "custom" : (`${query.days}` as RangeChoice)} onChange={onRange} />
        {custom && (
          <CustomRange
            // Re-initialise the inputs whenever the server returns a different window.
            key={`${period.date_from}|${period.date_to}`}
            from={period.date_from}
            to={period.date_to}
            min={bounds.date_from}
            max={bounds.date_to}
            onApply={(from, to) => onChange({ from, to })}
          />
        )}
        <p className="flex min-w-0 items-center gap-1.5 text-xs text-ink-muted" aria-live="polite">
          <CalendarRange aria-hidden className="size-3.5 shrink-0 text-ink-subtle" />
          <span>
            <span className="font-medium text-ink">{formatDateRange(period.date_from, period.date_to)}</span> ({formatInteger(period.days)}{" "}
            days) ·{" "}
            {previous ? (
              <>compared with {formatDateRange(previous.date_from, previous.date_to)}</>
            ) : (
              <>no earlier period of the same length in the data</>
            )}
          </span>
        </p>
      </div>

      <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-[11rem_11rem_14rem_auto_auto] lg:items-center">
        <Select label="Store" value={query.store ?? ""} onChange={(value) => onChange({ store: value || null })}>
          <option value="">All stores</option>
          {facets.stores.map((store) => (
            <option key={store} value={store}>
              {formatStore(store)}
            </option>
          ))}
        </Select>
        <Select label="Category" value={query.category ?? ""} onChange={(value) => onChange({ category: value || null })}>
          <option value="">All categories</option>
          {facets.categories.map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
          ))}
        </Select>
        <Select label="Supplier" value={query.supplier ?? ""} onChange={(value) => onChange({ supplier: value || null })}>
          <option value="">All suppliers</option>
          {facets.suppliers.map((supplier) => (
            <option key={supplier.supplier_id} value={supplier.supplier_id}>
              {supplier.supplier_name}
            </option>
          ))}
        </Select>
        <SegmentedControl<PromotionFilter>
          label="Promotion"
          options={PROMOTION_OPTIONS}
          value={query.promotion}
          onChange={(promotion) => onChange({ promotion })}
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
      <p className="text-[11px] text-ink-subtle">
        Sales data covers {formatDateRange(bounds.date_from, bounds.date_to)}. Filters apply to every figure on this page.
      </p>
    </motion.section>
  );
}

interface CustomRangeProps {
  from: string;
  to: string;
  min: string;
  max: string;
  onApply: (from: string, to: string) => void;
}

export function CustomRange({ from: initialFrom, to: initialTo, min, max, onApply }: CustomRangeProps) {
  const [from, setFrom] = useState(initialFrom);
  const [to, setTo] = useState(initialTo);
  const valid = Boolean(from && to && from <= to);
  const changed = from !== initialFrom || to !== initialTo;
  const input =
    "h-9 rounded-lg border border-line bg-white px-2.5 text-[13px] text-ink shadow-sm hover:border-line-strong";

  function submit(event: FormEvent) {
    event.preventDefault();
    if (valid) onApply(from, to);
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-2" aria-label="Custom date range">
      <label className="flex items-center gap-1.5 text-xs text-ink-muted">
        From
        <input type="date" value={from} min={min} max={max} onChange={(e) => setFrom(e.target.value)} className={input} required />
      </label>
      <label className="flex items-center gap-1.5 text-xs text-ink-muted">
        to
        <input type="date" value={to} min={min} max={max} onChange={(e) => setTo(e.target.value)} className={input} required />
      </label>
      <button
        type="submit"
        disabled={!valid || !changed}
        className="h-9 rounded-lg bg-brand px-3 text-[13px] font-medium text-white shadow-sm hover:bg-brand-strong disabled:opacity-50"
      >
        Apply
      </button>
      {from && to && from > to && <span className="text-xs font-medium text-red-700">Start must be on or before end.</span>}
    </form>
  );
}
