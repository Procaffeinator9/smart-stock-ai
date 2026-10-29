import { PackagePlus } from "lucide-react";
import { connection } from "next/server";

import { DataError } from "@/components/shared/data-error";
import { cardClassName } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { apiGet, type ApiResult } from "@/lib/api";
import { classifyFailure, datasetDates, describeFreshness, sourceLabel } from "@/lib/dashboard/live-data";
import { parseQuery, toListParams, toPlanParams } from "@/lib/replenishment/query";
import type { RecommendationPage, ReplenishmentPlanResponse } from "@/lib/replenishment/types";

import { ReplenishmentDashboard } from "./replenishment-dashboard";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function Failure({ result }: { result: Extract<ApiResult<unknown>, { ok: false }> }) {
  const view = classifyFailure(result.kind, result.message, result.retryAfterSeconds);
  return (
    <DataError
      kind={view.kind}
      message={view.message}
      retryAfterSeconds={view.retryAfterSeconds}
      resetHref={view.kind === "invalid" ? "/replenishment" : undefined}
    />
  );
}

/**
 * Server component: two read-only requests in parallel (the simulated plan with counts, and one
 * page of recommendations). Nothing is ordered or written. No polling (retry is manual).
 */
export async function ReplenishmentResults({ searchParams }: { searchParams: SearchParams }) {
  await connection(); // per request: live data and today's date are never prerendered
  const now = new Date();
  const query = parseQuery(await searchParams);
  const [plan, list] = await Promise.all([
    apiGet<ReplenishmentPlanResponse>("/api/v1/replenishment/plan", toPlanParams(query)),
    apiGet<RecommendationPage>("/api/v1/replenishment", toListParams(query)),
  ]);

  if (!plan.ok) return <Failure result={plan} />;
  if (plan.data.status === "empty") {
    return (
      <div className={cardClassName}>
        <EmptyState
          icon={PackagePlus}
          title="Nothing to plan yet"
          description={`${plan.data.reason} Source: ${sourceLabel(plan.data.source)}.`}
          className="py-16"
        />
      </div>
    );
  }
  if (!list.ok) return <Failure result={list} />;

  return (
    <ReplenishmentDashboard
      plan={plan.data}
      list={list.data}
      query={query}
      freshness={describeFreshness(plan.data.freshness)}
      dates={datasetDates(plan.data.as_of, now)}
    />
  );
}
