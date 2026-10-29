import type { Metadata } from "next";
import { Suspense } from "react";

import { SupplierScorecardResults } from "@/components/suppliers/supplier-scorecard-results";
import { SupplierSkeleton } from "@/components/suppliers/supplier-skeleton";

export const metadata: Metadata = { title: "Suppliers" };

export default function SuppliersPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  // searchParams is read inside the Suspense boundary, so the page shell still prerenders.
  return (
    <Suspense fallback={<SupplierSkeleton />}>
      <SupplierScorecardResults searchParams={searchParams} />
    </Suspense>
  );
}
