import type { Metadata } from "next";
import { Suspense } from "react";

import { SupplierDetailResults } from "@/components/suppliers/supplier-detail-results";
import { SupplierSkeleton } from "@/components/suppliers/supplier-skeleton";

export const metadata: Metadata = { title: "Supplier" };

export default function SupplierPage({ params }: { params: Promise<{ supplierId: string }> }) {
  // params is read inside the Suspense boundary, so the page shell still prerenders.
  return (
    <Suspense fallback={<SupplierSkeleton label="Loading supplier…" />}>
      <SupplierDetailResults params={params} />
    </Suspense>
  );
}
