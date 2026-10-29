import type { Metadata } from "next";
import { Suspense } from "react";

import { SalesResults } from "@/components/sales/sales-results";
import { SalesSkeleton } from "@/components/sales/sales-skeleton";

export const metadata: Metadata = { title: "Sales" };

export default function SalesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  // searchParams is read inside the Suspense boundary, so the page shell still prerenders.
  return (
    <Suspense fallback={<SalesSkeleton />}>
      <SalesResults searchParams={searchParams} />
    </Suspense>
  );
}
