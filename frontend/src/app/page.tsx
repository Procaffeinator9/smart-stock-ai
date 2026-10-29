import type { Metadata } from "next";
import { Suspense } from "react";

import { OverviewResults } from "@/components/dashboard/overview-results";
import { OverviewSkeleton } from "@/components/dashboard/overview-skeleton";

export const metadata: Metadata = { title: "Overview" };

export default function OverviewPage() {
  // Live data is fetched inside the Suspense boundary, so the page shell still prerenders.
  return (
    <Suspense fallback={<OverviewSkeleton />}>
      <OverviewResults />
    </Suspense>
  );
}
