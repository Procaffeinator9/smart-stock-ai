"use client";

import { ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";

import { cn } from "@/lib/cn";
import { PAGE_SIZES } from "@/lib/inventory/query";
import { formatInteger } from "@/lib/format";

/** Page numbers to show, with null for a gap: 1 … 4 5 6 … 40 */
function pageWindow(page: number, totalPages: number): Array<number | null> {
  const pages = new Set([1, totalPages, page - 1, page, page + 1].filter((p) => p >= 1 && p <= totalPages));
  const sorted = [...pages].sort((a, b) => a - b);
  return sorted.flatMap((p, i) => (i > 0 && p - sorted[i - 1] > 1 ? [null, p] : [p]));
}

interface InventoryPaginationProps {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onPage: (page: number) => void;
  onPageSize: (pageSize: number) => void;
  /** Plural noun in "Showing 1–25 of 1,000 positions". */
  itemLabel?: string;
}

export function InventoryPagination({ page, pageSize, total, totalPages, onPage, onPageSize, itemLabel = "positions" }: InventoryPaginationProps) {
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  const button =
    "grid h-8 min-w-8 place-items-center rounded-lg px-2 text-xs font-medium tabular-nums transition-colors disabled:pointer-events-none disabled:opacity-40";

  return (
    <nav aria-label="Pagination" className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-3 text-xs text-ink-muted">
        <p aria-live="polite">
          Showing <span className="font-medium text-ink">{formatInteger(from)}–{formatInteger(to)}</span> of{" "}
          <span className="font-medium text-ink">{formatInteger(total)}</span> {itemLabel}
        </p>
        <label className="relative">
          <span className="sr-only">Rows per page</span>
          <select
            value={pageSize}
            onChange={(event) => onPageSize(Number(event.target.value))}
            className="h-8 appearance-none rounded-lg border border-line bg-white pl-2.5 pr-7 text-xs text-ink shadow-sm"
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size} / page
              </option>
            ))}
          </select>
          <ChevronDown aria-hidden className="pointer-events-none absolute right-2 top-1/2 size-3.5 -translate-y-1/2 text-ink-subtle" />
        </label>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => onPage(page - 1)} disabled={page <= 1} aria-label="Previous page" className={cn(button, "hover:bg-slate-100")}>
            <ChevronLeft aria-hidden className="size-4" />
          </button>
          {pageWindow(page, totalPages).map((p, i) =>
            p === null ? (
              <span key={`gap-${i}`} aria-hidden className="px-1 text-xs text-ink-subtle">
                …
              </span>
            ) : (
              <button
                key={p}
                type="button"
                onClick={() => onPage(p)}
                aria-current={p === page ? "page" : undefined}
                aria-label={`Page ${p}`}
                className={cn(button, p === page ? "bg-ink text-white" : "text-ink-muted hover:bg-slate-100 hover:text-ink")}
              >
                {p}
              </button>
            ),
          )}
          <button
            type="button"
            onClick={() => onPage(page + 1)}
            disabled={page >= totalPages}
            aria-label="Next page"
            className={cn(button, "hover:bg-slate-100")}
          >
            <ChevronRight aria-hidden className="size-4" />
          </button>
        </div>
      )}
    </nav>
  );
}
