import { ClipboardList } from "lucide-react";
import { connection } from "next/server";

import { DataError } from "@/components/shared/data-error";
import { cardClassName } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { apiGet, type ApiResult } from "@/lib/api";
import { classifyFailure, datasetDates, describeFreshness, sourceLabel } from "@/lib/dashboard/live-data";
import { parsePurchaseOrderQuery, toListParams, toSummaryParams } from "@/lib/purchase-orders/query";
import type { PurchaseOrderPage, PurchaseOrderSummaryResponse } from "@/lib/purchase-orders/types";

import { PurchaseOrderDashboard } from "./purchase-order-dashboard";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function Failure({ result }: { result: Extract<ApiResult<unknown>, { ok: false }> }) {
  const view = classifyFailure(result.kind, result.message, result.retryAfterSeconds);
  return (
    <DataError
      kind={view.kind}
      message={view.message}
      retryAfterSeconds={view.retryAfterSeconds}
      resetHref={view.kind === "invalid" ? "/purchase-orders" : undefined}
    />
  );
}

/**
 * Server component: reads the URL query and makes two requests in parallel (summary + one page of
 * orders). Only aggregates and one table page reach the browser. No polling (retry is manual).
 */
export async function PurchaseOrderResults({ searchParams }: { searchParams: SearchParams }) {
  await connection(); // per request: live data and today's date are never prerendered
  const now = new Date();
  const query = parsePurchaseOrderQuery(await searchParams);
  const [summary, orders] = await Promise.all([
    apiGet<PurchaseOrderSummaryResponse>("/api/v1/purchase-orders/summary", toSummaryParams(query)),
    apiGet<PurchaseOrderPage>("/api/v1/purchase-orders", toListParams(query)),
  ]);

  if (!summary.ok) return <Failure result={summary} />;
  if (!orders.ok) return <Failure result={orders} />;

  const data = summary.data;
  if (data.status === "empty") {
    return (
      <div className={cardClassName}>
        <EmptyState
          icon={ClipboardList}
          title="No purchase orders to analyse yet"
          description={`${data.reason} Source: ${sourceLabel(data.source)}.`}
          className="py-16"
        />
      </div>
    );
  }

  return (
    <PurchaseOrderDashboard
      summary={data}
      orders={orders.data}
      query={query}
      freshness={describeFreshness(data.freshness)}
      dates={datasetDates(data.as_of, now)}
    />
  );
}
