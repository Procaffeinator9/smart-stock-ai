import { apiGet } from "@/lib/api";
import { parseQuery, toApiParams } from "@/lib/inventory/query";
import type { InventoryPage } from "@/lib/inventory/types";

import { InventoryError } from "./inventory-error";
import { InventoryWorklist } from "./inventory-worklist";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

/** Server component: reads the URL query and fetches one page from the FastAPI data API. */
export async function InventoryResults({ searchParams }: { searchParams: SearchParams }) {
  const query = parseQuery(await searchParams);
  const result = await apiGet<InventoryPage>("/api/v1/inventory", toApiParams(query));
  if (!result.ok) return <InventoryError kind={result.kind} message={result.message} />;
  return <InventoryWorklist data={result.data} query={query} />;
}
