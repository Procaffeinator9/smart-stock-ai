import { ArrowLeft, SearchX, Truck } from "lucide-react";
import Link from "next/link";
import { connection } from "next/server";

import { DataError } from "@/components/shared/data-error";
import { cardClassName } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { apiGet } from "@/lib/api";
import { classifyFailure, datasetDates, describeFreshness, sourceLabel } from "@/lib/dashboard/live-data";
import type { SupplierDetailResponse } from "@/lib/suppliers/types";

import { SupplierDetailView } from "./supplier-detail-view";

const backLink = (
  <Link
    href="/suppliers"
    className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-1.5 text-sm font-medium text-ink shadow-sm hover:border-line-strong"
  >
    <ArrowLeft aria-hidden className="size-4" /> All suppliers
  </Link>
);

/** Server component: one request for the supplier's performance detail. No polling (retry is manual). */
export async function SupplierDetailResults({ params }: { params: Promise<{ supplierId: string }> }) {
  await connection(); // per request: live data and today's date are never prerendered
  const now = new Date();
  const { supplierId } = await params;
  const result = await apiGet<SupplierDetailResponse>(`/api/v1/suppliers/${encodeURIComponent(supplierId)}/performance`);

  if (!result.ok) {
    if (result.status === 404 || result.kind === "invalid") {
      return (
        <div className={cardClassName}>
          <EmptyState
            icon={SearchX}
            title="Supplier not found"
            description={`There is no supplier with the ID “${supplierId.slice(0, 40)}” in the data.`}
            action={backLink}
            className="py-16"
          />
        </div>
      );
    }
    const view = classifyFailure(result.kind, result.message, result.retryAfterSeconds);
    return <DataError kind={view.kind} message={view.message} retryAfterSeconds={view.retryAfterSeconds} />;
  }
  const data = result.data;
  if (data.status === "empty") {
    return (
      <div className={cardClassName}>
        <EmptyState
          icon={Truck}
          title="No supplier performance to show yet"
          description={`${data.reason} Source: ${sourceLabel(data.source)}.`}
          action={backLink}
          className="py-16"
        />
      </div>
    );
  }
  return <SupplierDetailView data={data} freshness={describeFreshness(data.freshness)} dates={datasetDates(data.as_of, now)} />;
}
