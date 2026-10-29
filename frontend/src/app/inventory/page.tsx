import type { Metadata } from "next";
import { Suspense } from "react";

import { InventoryResults } from "@/components/inventory/inventory-results";
import { InventorySkeleton } from "@/components/inventory/inventory-skeleton";

export const metadata: Metadata = { title: "Inventory" };

export default function InventoryPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  // searchParams is read inside the Suspense boundary, so the page shell still prerenders.
  return (
    <Suspense fallback={<InventorySkeleton />}>
      <InventoryResults searchParams={searchParams} />
    </Suspense>
  );
}
