"use client";

import { CalendarClock, ClipboardCheck, Hourglass, Siren, TriangleAlert } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { usePathname, useRouter } from "next/navigation";
import { useOptimistic, useRef, useState, useTransition } from "react";

import { DataNotice } from "@/components/dashboard/data-notice";
import { KpiCard } from "@/components/dashboard/kpi-cards";
import { fadeUp } from "@/components/ui/card";
import { cn } from "@/lib/cn";
import type { DatasetDates, FreshnessView } from "@/lib/dashboard/live-data";
import { formatCurrency, formatInteger } from "@/lib/format";
import { DEFAULT_QUERY, hasActiveFilters, nextSort, toSearchParams, type ReplenishmentQuery, type SortField } from "@/lib/replenishment/query";
import type { RecommendationPage, ReplenishmentPlan } from "@/lib/replenishment/types";

import { RecommendationsTable } from "./recommendations-table";
import { ReorderPlanCard } from "./reorder-plan-card";
import { ReplenishmentDefinitions } from "./replenishment-definitions";
import { ReplenishmentFilters } from "./replenishment-filters";

interface ReplenishmentDashboardProps {
  plan: ReplenishmentPlan;
  list: RecommendationPage;
  query: ReplenishmentQuery;
  freshness: FreshnessView;
  dates: DatasetDates;
}

export function ReplenishmentDashboard({ plan, list, query, freshness, dates }: ReplenishmentDashboardProps) {
  const router = useRouter();
  const pathname = usePathname();
  const reduceMotion = useReducedMotion();
  const [isPending, startTransition] = useTransition();
  // Controls reflect the new choice immediately; the rows update when the server responds.
  const [current, setCurrent] = useOptimistic(query);
  const [searchKey, setSearchKey] = useState(0);
  const tableRef = useRef<HTMLDivElement>(null);

  function navigate(next: ReplenishmentQuery) {
    const qs = toSearchParams(next).toString();
    startTransition(() => {
      setCurrent(next);
      router.push(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    });
  }
  const update = (patch: Partial<ReplenishmentQuery>) => navigate({ ...current, ...patch, page: 1 });
  const onSort = (field: SortField) => update(nextSort(current, field));
  const onPage = (page: number) => {
    navigate({ ...current, page });
    tableRef.current?.scrollIntoView({ block: "start", behavior: reduceMotion ? "auto" : "smooth" });
  };
  const clear = () => {
    setSearchKey((key) => key + 1);
    navigate({ ...DEFAULT_QUERY, sort: current.sort, order: current.order, pageSize: current.pageSize });
  };

  const { counts, settings } = plan;
  const p = plan.plan;
  const note = (text: string) => <span className="text-xs text-ink-subtle">{text}</span>;

  return (
    <motion.div initial="hidden" animate="show" variants={{ show: { transition: { staggerChildren: 0.06 } } }} className="space-y-5">
      <DataNotice meta={{ source: plan.source, seed: null }} freshness={freshness} dates={dates} definitionsHref="#replenishment-definitions" />

      <motion.p variants={fadeUp} className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-xl border border-line bg-surface px-4 py-2.5 text-xs text-ink-muted">
        <span className="font-semibold text-ink">Assumptions:</span>
        <span>estimated demand from the last {settings.demand_window_days} in-stock days (falls back to {settings.fallback_window_days.join(", then ")} days, then reorder settings)</span>
        <span aria-hidden>·</span>
        <span>target = reorder point + {settings.review_days} days of demand</span>
        <span aria-hidden>·</span>
        <span>minimum order quantity is a minimum, not a pack size</span>
        <span aria-hidden>·</span>
        <span>arrival at the supplier&apos;s stated lead time</span>
        <span aria-hidden>·</span>
        <span>
          <span className="font-semibold text-ink">Simulation only:</span> no purchase orders are created
        </span>
      </motion.p>

      <motion.div variants={{ show: { transition: { staggerChildren: 0.07 } } }} className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Critical positions"
          icon={Siren}
          accent="bg-red-50 text-red-600 ring-red-600/10"
          value={counts.by_priority.critical}
          format={formatInteger}
          definition=""
          delta={note(`${formatInteger(counts.by_priority.high)} high · ${formatInteger(counts.by_priority.medium)} medium`)}
          footer="Out of stock, or below safety stock with nothing arriving before the projected run-out."
        />
        <KpiCard
          label="Orders recommended"
          icon={ClipboardCheck}
          accent="bg-brand-soft text-brand ring-brand/10"
          value={p.lines}
          format={formatInteger}
          definition=""
          delta={note(`${formatInteger(p.units)} units · ${formatInteger(p.suppliers.length)} suppliers`)}
          footer={
            p.manual_review
              ? `${formatInteger(p.manual_review)} more need manual review (no recent demand).`
              : "Stock plus open orders at or below the reorder point."
          }
        />
        <KpiCard
          label="Simulated order cost"
          icon={CalendarClock}
          accent="bg-sky-50 text-sky-700 ring-sky-600/10"
          value={p.cost}
          format={formatCurrency}
          definition=""
          delta={note(`${formatInteger(p.raised_to_moq)} raised to a minimum order`)}
          footer="Quantity × product unit cost. An estimate for review; nothing is ordered."
        />
        <KpiCard
          label="Orders to expedite"
          icon={Hourglass}
          accent="bg-amber-50 text-amber-700 ring-amber-600/15"
          value={counts.by_action.expedite}
          format={formatInteger}
          definition=""
          delta={note(`${formatInteger(counts.by_action.watch)} more to watch`)}
          footer="Already on order, but late or due after the projected run-out. No duplicate order is suggested."
        />
      </motion.div>

      {p.shelf_life_warnings > 0 && (
        <motion.div
          variants={fadeUp}
          role="status"
          className="flex flex-wrap items-start gap-3 rounded-xl border border-amber-300/80 bg-amber-50 px-4 py-3 text-[13px] text-amber-950"
        >
          <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-amber-700" />
          <p className="min-w-0 flex-1">
            <span className="font-semibold">
              {formatInteger(p.shelf_life_warnings)} of {formatInteger(p.lines)} recommended orders exceed the product&apos;s shelf life.
            </span>{" "}
            The stock after ordering would last longer than the product keeps. Quantities are not capped automatically; review these lines
            before ordering.
          </p>
          <a href="#reorder-plan" className="font-medium text-amber-900 underline underline-offset-2 hover:text-amber-700">
            Review in the plan
          </a>
        </motion.div>
      )}

      <ReplenishmentFilters
        query={current}
        list={list}
        searchKey={searchKey}
        onChange={update}
        onClear={clear}
        active={hasActiveFilters(current)}
      />

      <div aria-busy={isPending} className="relative">
        {isPending && (
          <div role="progressbar" aria-label="Loading results" className="absolute inset-x-0 -top-3 z-10 h-0.5 overflow-hidden rounded-full bg-brand-soft">
            <div className="h-full w-1/3 animate-[indeterminate_1.1s_ease-in-out_infinite] bg-brand" />
          </div>
        )}
        <div className={cn("space-y-5 transition-opacity duration-200", isPending && "pointer-events-none opacity-55")}>
          <div ref={tableRef} className="scroll-mt-24">
            <RecommendationsTable page={list} query={current} onSort={onSort} onPage={onPage} onPageSize={(pageSize) => update({ pageSize })} onClear={clear} />
          </div>
          <ReorderPlanCard plan={plan} />
        </div>
      </div>

      <ReplenishmentDefinitions settings={settings} />
    </motion.div>
  );
}
