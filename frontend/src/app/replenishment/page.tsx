import type { Metadata } from "next";
import { Suspense } from "react";

import { ReplenishmentResults } from "@/components/replenishment/replenishment-results";
import { ReplenishmentSkeleton } from "@/components/replenishment/replenishment-skeleton";

export const metadata: Metadata = { title: "Replenishment" };

export default function ReplenishmentPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  // searchParams is read inside the Suspense boundary, so the page shell still prerenders.
  return (
    <Suspense fallback={<ReplenishmentSkeleton />}>
      <ReplenishmentResults searchParams={searchParams} />
    </Suspense>
  );
}
