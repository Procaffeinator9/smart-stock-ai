"use client";

import { Database, FlaskConical, TriangleAlert } from "lucide-react";
import { motion } from "motion/react";

import { fadeUp } from "@/components/ui/card";
import { useShell } from "@/components/shell/shell-context";
import { cn } from "@/lib/cn";
import { sourceLabel, type DatasetDates, type FreshnessView } from "@/lib/dashboard/live-data";
import type { SnapshotMeta } from "@/lib/dashboard/types";

const TONE = {
  fresh: "border-indigo-200/60 from-indigo-50/80 to-sky-50/60 text-indigo-950",
  unknown: "border-indigo-200/60 from-indigo-50/80 to-sky-50/60 text-indigo-950",
  stale: "border-amber-300/70 from-amber-50 to-orange-50/60 text-amber-950",
  failed: "border-red-300/70 from-red-50 to-amber-50/60 text-red-950",
} as const;

interface DataNoticeProps {
  meta: Pick<SnapshotMeta, "source" | "seed">;
  freshness: FreshnessView;
  dates: DatasetDates;
  /** Link "How it's calculated" to definitions on the page instead of opening the About dialog. */
  definitionsHref?: string;
}

/** Source, dataset date vs today, and freshness; warns when the snapshot is stale or a refresh failed. */
export function DataNotice({ meta, freshness, dates, definitionsHref }: DataNoticeProps) {
  const { openAbout } = useShell();
  const warn = freshness.tone === "stale" || freshness.tone === "failed";
  const Icon = warn ? TriangleAlert : meta.source === "synthetic" ? FlaskConical : Database;

  return (
    <motion.div
      variants={fadeUp}
      role={warn ? "status" : undefined}
      className={cn("rounded-xl border bg-gradient-to-r px-4 py-2.5 text-[13px]", TONE[freshness.tone])}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Icon aria-hidden className={cn("size-4 shrink-0", warn ? "text-current" : "text-brand")} />
        <p className="min-w-0 flex-1">
          <span className="font-semibold">Synthetic demo data</span> from{" "}
          <span className="font-semibold">{sourceLabel(meta.source)}</span>
          {meta.seed !== null && <> (seed {meta.seed})</>} · <span className="font-semibold">Data as of {dates.asOfLabel}</span>{" "}
          (latest inventory snapshot) · Today {dates.todayLabel}
          {dates.daysBehind > 0 && <> ({dates.daysBehind.toLocaleString("en-US")} days later)</>} · {freshness.summary}. Not real
          business results.
        </p>
        {definitionsHref ? (
          <a href={definitionsHref} className="text-[13px] font-medium text-brand hover:text-brand-strong">
            How it&apos;s calculated
          </a>
        ) : (
          <button type="button" onClick={openAbout} className="text-[13px] font-medium text-brand hover:text-brand-strong">
            How it&apos;s calculated
          </button>
        )}
      </div>
      {freshness.warning && <p className="mt-1 pl-7 font-medium">{freshness.warning}</p>}
    </motion.div>
  );
}
