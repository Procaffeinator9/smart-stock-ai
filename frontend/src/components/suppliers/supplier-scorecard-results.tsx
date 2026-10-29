import { Truck } from "lucide-react";
import { connection } from "next/server";

import { DataError } from "@/components/shared/data-error";
import { cardClassName } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { apiGet } from "@/lib/api";
import { classifyFailure, datasetDates, describeFreshness, sourceLabel } from "@/lib/dashboard/live-data";
import { parseSupplierQuery, toSearchParams } from "@/lib/suppliers/query";
import type { SupplierScorecardResponse } from "@/lib/suppliers/types";

import { SupplierScorecardView } from "./supplier-scorecard-view";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

/** Server component: one request (the scorecard: one aggregated row per supplier). No polling. */
export async function SupplierScorecardResults({ searchParams }: { searchParams: SearchParams }) {
  await connection(); // per request: live data and today's date are never prerendered
  const now = new Date();
  const query = parseSupplierQuery(await searchParams);
  const result = await apiGet<SupplierScorecardResponse>("/api/v1/suppliers/performance", toSearchParams(query));

  if (!result.ok) {
    const view = classifyFailure(result.kind, result.message, result.retryAfterSeconds);
    return (
      <DataError
        kind={view.kind}
        message={view.message}
        retryAfterSeconds={view.retryAfterSeconds}
        resetHref={view.kind === "invalid" ? "/suppliers" : undefined}
      />
    );
  }
  const data = result.data;
  if (data.status === "empty") {
    return (
      <div className={cardClassName}>
        <EmptyState
          icon={Truck}
          title="No supplier performance to show yet"
          description={`${data.reason} Source: ${sourceLabel(data.source)}.`}
          className="py-16"
        />
      </div>
    );
  }
  return (
    <SupplierScorecardView data={data} query={query} freshness={describeFreshness(data.freshness)} dates={datasetDates(data.as_of, now)} />
  );
}
