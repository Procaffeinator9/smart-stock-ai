import type { Metadata } from "next";
import { Suspense } from "react";

import { PurchaseOrderResults } from "@/components/purchase-orders/purchase-order-results";
import { PurchaseOrderSkeleton } from "@/components/purchase-orders/purchase-order-skeleton";

export const metadata: Metadata = { title: "Purchase Orders" };

export default function PurchaseOrdersPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  // searchParams is read inside the Suspense boundary, so the page shell still prerenders.
  return (
    <Suspense fallback={<PurchaseOrderSkeleton />}>
      <PurchaseOrderResults searchParams={searchParams} />
    </Suspense>
  );
}
