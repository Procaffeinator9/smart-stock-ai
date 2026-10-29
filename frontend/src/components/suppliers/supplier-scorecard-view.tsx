"use client";

import { CalendarCheck, PackageX, TriangleAlert, Wallet, Search, X } from "lucide-react";
import { motion } from "motion/react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useOptimistic, useRef, useState, useTransition } from "react";

import { DataNotice } from "@/components/dashboard/data-notice";
import { KpiCard } from "@/components/dashboard/kpi-cards";
import { cardClassName, fadeUp } from "@/components/ui/card";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { cn } from "@/lib/cn";
import type { DatasetDates, FreshnessView } from "@/lib/dashboard/live-data";
import { formatCurrencyCompact, formatInteger, formatPercent } from "@/lib/format";
import {
  DEFAULT_SUPPLIER_QUERY,
  hasActiveFilters,
  nextSort,
  toSearchParams,
  type AttentionFilter,
  type ScoreSortField,
  type SupplierQuery,
} from "@/lib/suppliers/query";
import type { SupplierScorecard } from "@/lib/suppliers/types";

import { ReliabilityChart } from "./reliability-chart";
import { ScorecardTable } from "./scorecard-table";
import { SupplierDefinitions } from "./supplier-definitions";

const SEARCH_DEBOUNCE_MS = 350;

const ATTENTION_OPTIONS = [
  { value: "all" as const, label: "All suppliers" },
  { value: "flagged" as const, label: "Needs attention", title: "At least one flag" },
  { value: "clear" as const, label: "No flags" },
];

interface SupplierScorecardViewProps {
  data: SupplierScorecard;
  query: SupplierQuery;
  freshness: FreshnessView;
  dates: DatasetDates;
}

export function SupplierScorecardView({ data, query, freshness, dates }: SupplierScorecardViewProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [isPending, startTransition] = useTransition();
  // Controls reflect the new choice immediately; the rows update when the server responds.
  const [current, setCurrent] = useOptimistic(query);
  const [searchKey, setSearchKey] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  function navigate(next: SupplierQuery) {
    const qs = toSearchParams(next).toString();
    startTransition(() => {
      setCurrent(next);
      router.push(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    });
  }
  const update = (patch: Partial<SupplierQuery>) => navigate({ ...current, ...patch });
  const onSort = (field: ScoreSortField) => update(nextSort(current, field));
  const onSearch = (value: string) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => update({ search: value }), SEARCH_DEBOUNCE_MS);
  };
  const clear = () => {
    setSearchKey((key) => key + 1);
    navigate({ ...DEFAULT_SUPPLIER_QUERY, sort: current.sort, order: current.order });
  };

  const { network } = data;
  const active = hasActiveFilters(current);

  return (
    <motion.div initial="hidden" animate="show" variants={{ show: { transition: { staggerChildren: 0.06 } } }} className="space-y-5">
      <DataNotice meta={{ source: data.source, seed: null }} freshness={freshness} dates={dates} definitionsHref="#supplier-definitions" />

      <motion.div variants={{ show: { transition: { staggerChildren: 0.07 } } }} className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Need attention"
          icon={TriangleAlert}
          accent="bg-amber-50 text-amber-700 ring-amber-600/15"
          value={network.flagged}
          format={formatInteger}
          definition=""
          delta={<span className="text-xs text-ink-subtle">of {formatInteger(network.suppliers)} suppliers</span>}
          footer="At least one flag. Each flag states its rule and numbers; there is no combined score."
        />
        <KpiCard
          label="Network on-time rate"
          icon={CalendarCheck}
          accent="bg-emerald-50 text-emerald-700 ring-emerald-600/15"
          value={network.on_time_rate ?? 0}
          format={formatPercent}
          definition=""
          delta={
            <span className="text-xs text-ink-subtle">
              {formatInteger(network.on_time)} of {formatInteger(network.sample_size)} orders
            </span>
          }
          footer="Observed, with overdue open orders counted as late (the Purchase Orders definition)."
        />
        <KpiCard
          label="Spend"
          icon={Wallet}
          accent="bg-brand-soft text-brand ring-brand/10"
          value={network.spend}
          format={formatCurrencyCompact}
          definition=""
          delta={<span className="text-xs text-ink-subtle">{formatInteger(network.orders)} orders</span>}
          footer="Order value at unit cost, excluding cancelled orders."
        />
        <KpiCard
          label="At-risk stock positions"
          icon={PackageX}
          accent="bg-red-50 text-red-600 ring-red-600/10"
          value={network.at_risk_positions}
          format={formatInteger}
          definition=""
          delta={<span className="text-xs text-ink-subtle">of {formatInteger(network.positions)} store positions</span>}
          footer="Below safety stock or out of stock on the as-of date."
        />
      </motion.div>

      <motion.section variants={fadeUp} aria-label="Supplier filters" className={cn(cardClassName, "flex flex-wrap items-center gap-3 p-4 sm:p-5")}>
        <label className="relative block w-full sm:w-72">
          <span className="sr-only">Search suppliers</span>
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-subtle" />
          <input
            key={searchKey}
            type="search"
            defaultValue={current.search}
            onChange={(event) => onSearch(event.target.value)}
            maxLength={100}
            placeholder="Search supplier name or ID…"
            className="h-9 w-full rounded-lg border border-line bg-white pl-9 pr-3 text-[13px] text-ink shadow-sm placeholder:text-ink-subtle hover:border-line-strong"
          />
        </label>
        <SegmentedControl<AttentionFilter>
          label="Attention"
          options={ATTENTION_OPTIONS}
          value={current.attention}
          onChange={(attention) => update({ attention })}
        />
        {active && (
          <button
            type="button"
            onClick={clear}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-[13px] font-medium text-ink-muted hover:bg-slate-100 hover:text-ink"
          >
            <X aria-hidden className="size-4" /> Clear filters
          </button>
        )}
        <p className="w-full text-[11px] text-ink-subtle sm:ml-auto sm:w-auto" aria-live="polite">
          {formatInteger(data.total)} of {formatInteger(network.suppliers)} suppliers shown. Figures cover every order, sale and stock position in
          the data.
        </p>
      </motion.section>

      <div aria-busy={isPending} className="relative">
        {isPending && (
          <div role="progressbar" aria-label="Loading results" className="absolute inset-x-0 -top-3 z-10 h-0.5 overflow-hidden rounded-full bg-brand-soft">
            <div className="h-full w-1/3 animate-[indeterminate_1.1s_ease-in-out_infinite] bg-brand" />
          </div>
        )}
        <div className={cn("space-y-5 transition-opacity duration-200", isPending && "pointer-events-none opacity-55")}>
          <ScorecardTable rows={data.items} query={current} onSort={onSort} onClear={clear} />
          <ReliabilityChart rows={data.items} />
        </div>
      </div>

      <SupplierDefinitions />
    </motion.div>
  );
}
