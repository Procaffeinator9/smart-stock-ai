"use client";

import { DataError } from "@/components/shared/data-error";
import type { ApiErrorKind } from "@/lib/api";

/** Inventory keeps its original states: an invalid filter offers a reset; anything else, a retry. */
export function InventoryError({ kind, message }: { kind: ApiErrorKind; message: string }) {
  return <DataError kind={kind} message={message} resetHref={kind === "invalid" ? "/inventory" : undefined} />;
}
