"use client";

import { Search, X } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useRef } from "react";

import { Select } from "@/components/inventory/inventory-filters";
import { cardClassName, fadeUp } from "@/components/ui/card";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { cn } from "@/lib/cn";
import { formatInteger, formatStore } from "@/lib/format";
import { PRIORITIES, VIEW_ACTIONS, type ReplenishmentQuery, type View } from "@/lib/replenishment/query";
import type { Priority, RecommendationPage } from "@/lib/replenishment/types";

import { PRIORITY_STYLE } from "./priority-badge";

const SEARCH_DEBOUNCE_MS = 350;

interface ReplenishmentFiltersProps {
  query: ReplenishmentQuery;
  list: RecommendationPage;
  searchKey: number;
  onChange: (patch: Partial<ReplenishmentQuery>) => void;
  onClear: () => void;
  active: boolean;
}

export function ReplenishmentFilters({ query, list, searchKey, onChange, onClear, active }: ReplenishmentFiltersProps) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const { by_action: actions, by_priority: priorities } = list.counts;
  const count = (view: View) => VIEW_ACTIONS[view].reduce((sum, a) => sum + actions[a], 0);
  const views: Array<{ value: View; label: string; title?: string }> = [
    { value: "needs_action", label: `Needs action ${formatInteger(count("needs_action"))}`, title: "Order now and Expedite" },
    { value: "order", label: `Order now ${formatInteger(actions.order)}` },
    { value: "expedite", label: `Expedite ${formatInteger(actions.expedite)}` },
    { value: "watch", label: `Watch ${formatInteger(actions.watch)}`, title: "Projected to reach the reorder point within 3 days" },
    { value: "all", label: "All" },
  ];

  function onSearch(value: string) {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => onChange({ search: value }), SEARCH_DEBOUNCE_MS);
  }

  function togglePriority(priority: Priority) {
    const next = query.priorities.includes(priority) ? query.priorities.filter((p) => p !== priority) : [...query.priorities, priority];
    onChange({ priorities: PRIORITIES.filter((p) => next.includes(p)) });
  }

  return (
    <motion.section variants={fadeUp} aria-label="Replenishment filters" className={cn(cardClassName, "space-y-3 p-4 sm:p-5")}>
      <div className="overflow-x-auto">
        <SegmentedControl label="Show" options={views} value={query.view} onChange={(view) => onChange({ view })} />
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_11rem_11rem_14rem_auto]">
        <label className="relative block sm:col-span-2 lg:col-span-1">
          <span className="sr-only">Search products</span>
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-subtle" />
          <input
            key={searchKey}
            type="search"
            defaultValue={query.search}
            onChange={(event) => onSearch(event.target.value)}
            maxLength={100}
            placeholder="Search product, SKU or ID…"
            className="h-9 w-full rounded-lg border border-line bg-white pl-9 pr-3 text-[13px] text-ink shadow-sm placeholder:text-ink-subtle hover:border-line-strong"
          />
        </label>
        <Select label="Store" value={query.store ?? ""} onChange={(v) => onChange({ store: v || null })}>
          <option value="">All stores</option>
          {list.facets.stores.map((store) => (
            <option key={store} value={store}>
              {formatStore(store)}
            </option>
          ))}
        </Select>
        <Select label="Category" value={query.category ?? ""} onChange={(v) => onChange({ category: v || null })}>
          <option value="">All categories</option>
          {list.facets.categories.map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
          ))}
        </Select>
        <Select label="Supplier" value={query.supplier ?? ""} onChange={(v) => onChange({ supplier: v || null })}>
          <option value="">All suppliers</option>
          {list.facets.suppliers.map((s) => (
            <option key={s.supplier_id} value={s.supplier_id}>
              {s.supplier_name}
            </option>
          ))}
        </Select>
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

      <div role="group" aria-label="Filter by priority" className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          aria-pressed={query.priorities.length === 0}
          onClick={() => onChange({ priorities: [] })}
          className={cn(
            "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition-colors",
            query.priorities.length === 0 ? "border-ink bg-ink text-white" : "border-line bg-white text-ink-muted hover:border-line-strong hover:text-ink",
          )}
        >
          All priorities
        </button>
        {PRIORITIES.map((priority) => {
          const pressed = query.priorities.includes(priority);
          const style = PRIORITY_STYLE[priority];
          return (
            <button
              key={priority}
              type="button"
              aria-pressed={pressed}
              onClick={() => togglePriority(priority)}
              className={cn(
                "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition-colors",
                pressed ? "border-brand/30 bg-brand-soft text-brand-strong" : "border-line bg-white text-ink-muted hover:border-line-strong hover:text-ink",
              )}
            >
              <span aria-hidden className={cn("size-2 rounded-full", style.dot)} />
              {style.label} <span className="tabular-nums opacity-70">{formatInteger(priorities[priority])}</span>
            </button>
          );
        })}
      </div>
      <p className="text-[11px] text-ink-subtle">
        Watch rows (projected to reach the reorder point within 3 days) are hidden unless you choose Watch or All. Store, category,
        supplier and search also apply to the simulated plan.
      </p>
    </motion.section>
  );
}
