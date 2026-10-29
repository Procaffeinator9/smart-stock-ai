"use client";

import { ArrowDownWideNarrow, ArrowUpNarrowWide, ChevronDown, Search, X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

import { POSITION_STATUS } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import type { PositionStatus } from "@/lib/dashboard/types";
import { STATUSES, type InventoryQuery, type SortField } from "@/lib/inventory/query";
import { formatInteger, formatStore } from "@/lib/format";

export const SORT_LABELS: Record<SortField, string> = {
  severity: "Urgency",
  product_name: "Product",
  store_id: "Store",
  category: "Category",
  available: "Available",
  days_of_cover: "Days of cover",
  reorder_point: "Reorder point",
  safety_stock: "Safety stock",
  inventory_position: "Inventory position",
  next_delivery: "Next delivery",
};

const SEARCH_DEBOUNCE_MS = 350;

export function Select({ label, value, onChange, children }: { label: string; value: string; onChange: (value: string) => void; children: ReactNode }) {
  return (
    <label className="relative block min-w-0">
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 w-full appearance-none rounded-lg border border-line bg-white py-0 pl-3 pr-8 text-[13px] text-ink shadow-sm transition-colors hover:border-line-strong"
      >
        {children}
      </select>
      <ChevronDown aria-hidden className="pointer-events-none absolute right-2.5 top-1/2 size-4 -translate-y-1/2 text-ink-subtle" />
    </label>
  );
}

interface InventoryFiltersProps {
  query: InventoryQuery;
  facets: { stores: string[]; categories: string[] };
  summary: Record<PositionStatus, number>;
  onChange: (patch: Partial<InventoryQuery>) => void;
  onClear: () => void;
  searchKey: number;
  active: boolean;
}

export function InventoryFilters({ query, facets, summary, onChange, onClear, searchKey, active }: InventoryFiltersProps) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  function onSearch(value: string) {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => onChange({ search: value }), SEARCH_DEBOUNCE_MS);
  }

  function toggleStatus(status: PositionStatus) {
    const next = query.status.includes(status) ? query.status.filter((s) => s !== status) : [...query.status, status];
    onChange({ status: STATUSES.filter((s) => next.includes(s)) });
  }

  const total = STATUSES.reduce((sum, s) => sum + summary[s], 0);

  return (
    <div className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_11rem_11rem_auto]">
        <label className="relative block sm:col-span-2 lg:col-span-1">
          <span className="sr-only">Search inventory</span>
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-subtle" />
          <input
            key={searchKey}
            type="search"
            defaultValue={query.search}
            onChange={(event) => onSearch(event.target.value)}
            maxLength={100}
            placeholder="Search product, SKU, ID or supplier…"
            className="h-9 w-full rounded-lg border border-line bg-white pl-9 pr-3 text-[13px] text-ink shadow-sm placeholder:text-ink-subtle hover:border-line-strong"
          />
        </label>
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
        <div className="flex gap-2 sm:col-span-2 lg:col-span-1 lg:hidden">
          <div className="flex-1">
            <Select label="Sort by" value={query.sort} onChange={(value) => onChange({ sort: value as SortField })}>
              {Object.entries(SORT_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  Sort: {label}
                </option>
              ))}
            </Select>
          </div>
          <button
            type="button"
            onClick={() => onChange({ order: query.order === "asc" ? "desc" : "asc" })}
            aria-label={query.order === "asc" ? "Sorted ascending, switch to descending" : "Sorted descending, switch to ascending"}
            className="grid size-9 shrink-0 place-items-center rounded-lg border border-line bg-white text-ink-muted shadow-sm hover:text-ink"
          >
            {query.order === "asc" ? <ArrowUpNarrowWide aria-hidden className="size-4" /> : <ArrowDownWideNarrow aria-hidden className="size-4" />}
          </button>
        </div>
        {active && (
          <button
            type="button"
            onClick={onClear}
            className="hidden h-9 items-center gap-1.5 rounded-lg px-3 text-[13px] font-medium text-ink-muted hover:bg-slate-100 hover:text-ink lg:inline-flex"
          >
            <X aria-hidden className="size-4" /> Clear
          </button>
        )}
      </div>

      <div role="group" aria-label="Filter by stock status" className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          aria-pressed={query.status.length === 0}
          onClick={() => onChange({ status: [] })}
          className={cn(
            "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition-colors",
            query.status.length === 0 ? "border-ink bg-ink text-white" : "border-line bg-white text-ink-muted hover:border-line-strong hover:text-ink",
          )}
        >
          All <span className="tabular-nums opacity-70">{formatInteger(total)}</span>
        </button>
        {STATUSES.map((status) => {
          const pressed = query.status.includes(status);
          const style = POSITION_STATUS[status];
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
              <span aria-hidden className={cn("size-2 rounded-full", style.dot)} />
              {style.label}{" "}
              <span className="tabular-nums opacity-70">{formatInteger(summary[status])}</span>
            </button>
          );
        })}
        {active && (
          <button
            type="button"
            onClick={onClear}
            className="inline-flex h-8 items-center gap-1 rounded-full px-2.5 text-xs font-medium text-ink-muted hover:bg-slate-100 hover:text-ink lg:hidden"
          >
            <X aria-hidden className="size-3.5" /> Clear filters
          </button>
        )}
      </div>
    </div>
  );
}
