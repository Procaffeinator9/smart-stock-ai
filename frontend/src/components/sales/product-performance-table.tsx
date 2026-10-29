"use client";

import { ArrowDown, ArrowUp, ArrowUpDown, PackageSearch, Search } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useRef, type ReactNode } from "react";

import { InventoryPagination } from "@/components/inventory/inventory-pagination";
import { cardClassName, fadeUp } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/cn";
import { formatCurrency, formatCurrencyPrecise, formatInteger, formatPercent } from "@/lib/format";
import type { ProductSortField, SalesQuery } from "@/lib/sales/query";
import type { ProductPerformance, ProductPerformancePage } from "@/lib/sales/types";

import { ChangeText } from "./change-text";

const SEARCH_DEBOUNCE_MS = 350;

const percentOrDash = (value: number | null) => (value === null ? "—" : formatPercent(value));

interface Column {
  field: ProductSortField;
  label: string;
  align?: "right";
  render: (row: ProductPerformance) => ReactNode;
}

const COLUMNS: Column[] = [
  {
    field: "revenue",
    label: "Revenue",
    align: "right",
    render: (r) => (
      <>
        <p className="font-semibold tabular-nums text-ink">{formatCurrency(r.revenue)}</p>
        <p className="text-[11px] tabular-nums text-ink-subtle">{percentOrDash(r.revenue_share)} of total</p>
      </>
    ),
  },
  { field: "units", label: "Units", align: "right", render: (r) => <span className="tabular-nums text-ink">{formatInteger(r.units)}</span> },
  {
    field: "gross_margin",
    label: "Margin",
    align: "right",
    render: (r) => (
      <>
        <p className="tabular-nums text-ink">{formatCurrency(r.gross_margin)}</p>
        <p className="text-[11px] tabular-nums text-ink-subtle">{percentOrDash(r.margin_rate)}</p>
      </>
    ),
  },
  {
    field: "avg_unit_price",
    label: "Avg price",
    align: "right",
    render: (r) => <span className="tabular-nums text-ink-muted">{r.avg_unit_price === null ? "—" : formatCurrencyPrecise(r.avg_unit_price)}</span>,
  },
  {
    field: "promo_revenue_share",
    label: "Promo",
    align: "right",
    render: (r) => <span className="tabular-nums text-ink-muted">{percentOrDash(r.promo_revenue_share)}</span>,
  },
  {
    field: "stockout_days",
    label: "Stockout days",
    align: "right",
    render: (r) => (
      <span
        className={cn("tabular-nums", r.stockout_days ? "font-medium text-red-700" : "text-ink-subtle")}
        title="Store-days that ended with no available units"
      >
        {r.stockout_days ? formatInteger(r.stockout_days) : "—"}
      </span>
    ),
  },
  {
    field: "revenue_change",
    label: "Change",
    align: "right",
    render: (r) => <ChangeText change={r.revenue_change} fallback={<span className="text-ink-subtle">—</span>} />,
  },
];

interface ProductPerformanceTableProps {
  page: ProductPerformancePage;
  query: SalesQuery;
  searchKey: number;
  onSearch: (search: string) => void;
  onSort: (field: ProductSortField) => void;
  onPage: (page: number) => void;
  onPageSize: (pageSize: number) => void;
  onClear: () => void;
}

export function ProductPerformanceTable({ page, query, searchKey, onSearch, onSort, onPage, onPageSize, onClear }: ProductPerformanceTableProps) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  function search(value: string) {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => onSearch(value), SEARCH_DEBOUNCE_MS);
  }

  const secondary = "rounded-lg border border-line bg-white px-3 py-1.5 text-sm font-medium text-ink shadow-sm hover:border-line-strong";

  return (
    <motion.section variants={fadeUp} aria-labelledby="product-performance-title" className={cn(cardClassName, "overflow-hidden")}>
      <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-end sm:justify-between sm:p-5">
        <div>
          <h2 id="product-performance-title" className="text-[15px] font-semibold tracking-tight text-ink">
            Product performance
          </h2>
          <p className="mt-0.5 text-[13px] text-ink-muted">
            Every product matching the filters, including those with no sales. Change compares revenue with the previous period.
          </p>
        </div>
        <label className="relative block sm:w-72">
          <span className="sr-only">Search products</span>
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-subtle" />
          <input
            key={searchKey}
            type="search"
            defaultValue={query.search}
            onChange={(event) => search(event.target.value)}
            maxLength={100}
            placeholder="Search product, SKU or ID…"
            className="h-9 w-full rounded-lg border border-line bg-white pl-9 pr-3 text-[13px] text-ink shadow-sm placeholder:text-ink-subtle hover:border-line-strong"
          />
        </label>
      </div>

      {page.total === 0 ? (
        <EmptyState
          icon={PackageSearch}
          title="No products match"
          description="Try a different search term or fewer filters."
          action={
            <button type="button" onClick={onClear} className={secondary}>
              Clear filters
            </button>
          }
          className="border-t border-line py-14"
        />
      ) : page.items.length === 0 ? (
        <EmptyState
          icon={PackageSearch}
          title={`Page ${page.page} is past the end`}
          description={`There are ${page.total_pages} pages for these filters.`}
          action={
            <button type="button" onClick={() => onPage(page.total_pages)} className={secondary}>
              Go to last page
            </button>
          }
          className="border-t border-line py-14"
        />
      ) : (
        <>
          <DesktopTable rows={page.items} query={query} onSort={onSort} />
          <MobileList rows={page.items} />
        </>
      )}

      {page.total > 0 && (
        <div className="border-t border-line px-4 py-3 sm:px-5">
          <InventoryPagination
            page={query.page}
            pageSize={query.pageSize}
            total={page.total}
            totalPages={page.total_pages}
            onPage={onPage}
            onPageSize={onPageSize}
            itemLabel="products"
          />
        </div>
      )}
    </motion.section>
  );
}

function SortHeader({ field, label, align, query, onSort }: { field: ProductSortField; label: string; align?: "right"; query: SalesQuery; onSort: (field: ProductSortField) => void }) {
  const active = query.sort === field;
  const Icon = !active ? ArrowUpDown : query.order === "asc" ? ArrowUp : ArrowDown;
  return (
    <th
      scope="col"
      aria-sort={active ? (query.order === "asc" ? "ascending" : "descending") : "none"}
      className={cn("px-3 py-2 font-medium", align === "right" && "text-right")}
    >
      <button
        type="button"
        onClick={() => onSort(field)}
        className={cn("inline-flex items-center gap-1 rounded uppercase tracking-wide hover:text-ink", active && "text-ink", align === "right" && "flex-row-reverse")}
      >
        {label}
        <Icon aria-hidden className={cn("size-3", !active && "opacity-40")} />
      </button>
    </th>
  );
}

function DesktopTable({ rows, query, onSort }: { rows: ProductPerformance[]; query: SalesQuery; onSort: (field: ProductSortField) => void }) {
  return (
    <div className="hidden overflow-x-auto md:block">
      <table className="w-full min-w-[980px] text-left text-[13px]">
        <caption className="sr-only">Sales by product for the selected period. Column headers sort the table.</caption>
        <thead>
          <tr className="border-y border-line bg-slate-50/60 text-[11px] text-ink-subtle">
            <SortHeader field="product_name" label="Product" query={query} onSort={onSort} />
            <SortHeader field="category" label="Category" query={query} onSort={onSort} />
            {COLUMNS.map((column) => (
              <SortHeader key={column.field} field={column.field} label={column.label} align={column.align} query={query} onSort={onSort} />
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.product_id} className="border-b border-line transition-colors last:border-b-0 hover:bg-slate-50/70">
              <td className="max-w-[260px] px-3 py-2.5">
                <p className="truncate font-medium text-ink">{row.product_name}</p>
                <p className="truncate text-xs text-ink-subtle">
                  {row.sku} · {row.supplier_name}
                </p>
              </td>
              <td className="whitespace-nowrap px-3 py-2.5 text-ink-muted">{row.category}</td>
              {COLUMNS.map((column) => (
                <td key={column.field} className={cn("whitespace-nowrap px-3 py-2.5", column.align === "right" && "text-right")}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MobileList({ rows }: { rows: ProductPerformance[] }) {
  return (
    <ul className="divide-y divide-line border-t border-line md:hidden">
      {rows.map((row) => (
        <li key={row.product_id} className="px-4 py-3.5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-ink">{row.product_name}</p>
              <p className="truncate text-xs text-ink-subtle">
                {row.sku} · {row.category}
              </p>
            </div>
            <div className="text-right">
              <p className="text-sm font-semibold tabular-nums text-ink">{formatCurrency(row.revenue)}</p>
              <ChangeText change={row.revenue_change} className="text-xs" />
            </div>
          </div>
          <dl className="mt-3 grid grid-cols-3 gap-x-3 gap-y-2">
            {(
              [
                ["Units", formatInteger(row.units)],
                ["Margin", percentOrDash(row.margin_rate)],
                ["Avg price", row.avg_unit_price === null ? "—" : formatCurrencyPrecise(row.avg_unit_price)],
                ["Promo", percentOrDash(row.promo_revenue_share)],
                ["Stockout days", row.stockout_days ? formatInteger(row.stockout_days) : "—"],
                ["Supplier", row.supplier_name],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="min-w-0">
                <dt className="truncate text-[11px] text-ink-subtle">{label}</dt>
                <dd className="truncate text-[13px] font-medium tabular-nums text-ink">{value}</dd>
              </div>
            ))}
          </dl>
        </li>
      ))}
    </ul>
  );
}
