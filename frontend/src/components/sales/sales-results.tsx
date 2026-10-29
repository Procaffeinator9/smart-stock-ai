import { DatabaseBackup } from "lucide-react";
import { connection } from "next/server";

import { DataError } from "@/components/shared/data-error";
import { cardClassName } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { apiGet, type ApiResult } from "@/lib/api";
import { classifyFailure, datasetDates, describeFreshness, sourceLabel } from "@/lib/dashboard/live-data";
import { parseSalesQuery, toProductParams, toSummaryParams } from "@/lib/sales/query";
import type { ProductPerformancePage, SalesSummaryResponse } from "@/lib/sales/types";

import { SalesDashboard } from "./sales-dashboard";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function Failure({ result }: { result: Extract<ApiResult<unknown>, { ok: false }> }) {
  const view = classifyFailure(result.kind, result.message, result.retryAfterSeconds);
  return (
    <DataError
      kind={view.kind}
      message={view.message}
      retryAfterSeconds={view.retryAfterSeconds}
      resetHref={view.kind === "invalid" ? "/sales" : undefined}
    />
  );
}

/**
 * Server component: reads the URL query and makes two requests in parallel (summary + one page of
 * products). Only aggregates and one table page reach the browser. No polling (retry is manual).
 */
export async function SalesResults({ searchParams }: { searchParams: SearchParams }) {
  await connection(); // per request: live data and today's date are never prerendered
  const now = new Date();
  const query = parseSalesQuery(await searchParams);
  const [summary, products] = await Promise.all([
    apiGet<SalesSummaryResponse>("/api/v1/sales/summary", toSummaryParams(query)),
    apiGet<ProductPerformancePage>("/api/v1/sales/products", toProductParams(query)),
  ]);

  if (!summary.ok) return <Failure result={summary} />;
  if (!products.ok) return <Failure result={products} />;

  const data = summary.data;
  if (data.status === "empty") {
    return (
      <div className={cardClassName}>
        <EmptyState
          icon={DatabaseBackup}
          title="No sales to analyse yet"
          description={`${data.reason} Source: ${sourceLabel(data.source)}.`}
          className="py-16"
        />
      </div>
    );
  }

  return (
    <SalesDashboard
      summary={data}
      products={products.data}
      query={query}
      freshness={describeFreshness(data.freshness)}
      dates={datasetDates(data.as_of ?? data.bounds.date_to, now)}
    />
  );
}
