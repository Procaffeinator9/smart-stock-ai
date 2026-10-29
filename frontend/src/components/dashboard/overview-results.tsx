import { DatabaseBackup } from "lucide-react";
import { connection } from "next/server";

import { DataError } from "@/components/shared/data-error";
import { cardClassName } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { classifyFailure, datasetDates, describeFreshness, sourceLabel } from "@/lib/dashboard/live-data";
import { fetchOverview } from "@/lib/dashboard/overview";
import type { OverviewData } from "@/lib/dashboard/types";

import { OverviewDashboard } from "./overview-dashboard";

/** Server component: one GET /api/v1/overview per page view; no polling (retry is manual). */
export async function OverviewResults() {
  await connection(); // per request: live data and today's date are never prerendered
  const now = new Date();
  const result = await fetchOverview();

  if (!result.ok) {
    const view = classifyFailure(result.kind, result.message, result.retryAfterSeconds);
    return <DataError kind={view.kind} message={view.message} retryAfterSeconds={view.retryAfterSeconds} />;
  }

  const overview = result.data;
  if (overview.status === "empty") {
    return (
      <div className={cardClassName}>
        <EmptyState
          icon={DatabaseBackup}
          title="No data to summarise yet"
          description={`${overview.reason} Source: ${sourceLabel(overview.source)}.`}
          className="py-16"
        />
      </div>
    );
  }

  const data: OverviewData = {
    meta: overview.meta,
    kpis: overview.kpis,
    daily: overview.daily,
    alerts: overview.alerts,
    purchase_orders: overview.purchase_orders,
    store_health: overview.store_health,
    forecast: overview.forecast,
  };
  return (
    <OverviewDashboard
      data={data}
      freshness={describeFreshness(overview.freshness)}
      dates={datasetDates(data.meta.as_of, now)}
    />
  );
}
