"use client";

import { ArrowDown, ArrowDownWideNarrow, ArrowUp, ArrowUpDown, ArrowUpNarrowWide, ClipboardList, Search } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useRef } from "react";

import { Select } from "@/components/inventory/inventory-filters";
import { InventoryPagination } from "@/components/inventory/inventory-pagination";
import { cardClassName, fadeUp } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PurchaseOrderBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { formatCurrency, formatInteger, formatShortDate, formatStore } from "@/lib/format";
import type { OrderSortField, PurchaseOrderQuery } from "@/lib/purchase-orders/query";
import type { PurchaseOrder, PurchaseOrderPage } from "@/lib/purchase-orders/types";

const SEARCH_DEBOUNCE_MS = 350;

export const ORDER_SORT_LABELS: Record<OrderSortField, string> = {
  order_date: "Order date",
  expected_delivery_date: "Promised date",
  actual_delivery_date: "Delivery date",
  quantity_ordered: "Quantity",
  value: "Value",
  days_overdue: "Days overdue",
  days_late: "Days late",
  purchase_order_id: "Order ID",
};

const days = (n: number) => `${formatInteger(n)} ${n === 1 ? "day" : "days"}`;

/** Lateness as text and tone; colour is never the only signal. */
export function lateness(po: PurchaseOrder): { text: string; tone: string } {
  if (po.days_overdue !== null) return { text: `${days(po.days_overdue)} overdue`, tone: "font-semibold text-red-700" };
  if (po.days_late !== null) return { text: `${days(po.days_late)} late`, tone: "font-medium text-amber-700" };
  if (po.order_status === "DELIVERED") return { text: "On time", tone: "text-emerald-700" };
  if (po.order_status === "CANCELLED") return { text: "—", tone: "text-ink-subtle" };
  return { text: "Not yet due", tone: "text-ink-subtle" };
}

interface PurchaseOrderTableProps {
  page: PurchaseOrderPage;
  query: PurchaseOrderQuery;
  searchKey: number;
  onSearch: (search: string) => void;
  onSort: (field: OrderSortField) => void;
  onPage: (page: number) => void;
  onPageSize: (pageSize: number) => void;
  onClear: () => void;
}

export function PurchaseOrderTable({ page, query, searchKey, onSearch, onSort, onPage, onPageSize, onClear }: PurchaseOrderTableProps) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  function search(value: string) {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => onSearch(value), SEARCH_DEBOUNCE_MS);
  }

  const secondary = "rounded-lg border border-line bg-white px-3 py-1.5 text-sm font-medium text-ink shadow-sm hover:border-line-strong";
  // In the delivered-late view the lateness column sorts by days late; otherwise by days overdue.
  const lateField: OrderSortField = query.lateness === "late" ? "days_late" : "days_overdue";

  return (
    <motion.section variants={fadeUp} aria-labelledby="purchase-order-table-title" className={cn(cardClassName, "overflow-hidden")}>
      <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-end sm:justify-between sm:p-5">
        <div>
          <h2 id="purchase-order-table-title" className="text-[15px] font-semibold tracking-tight text-ink">
            Orders
          </h2>
          <p className="mt-0.5 text-[13px] text-ink-muted">
            {query.lateness === "overdue"
              ? "Open orders past their promised date."
              : query.lateness === "late"
                ? "Orders delivered after their promised date."
                : "Every order matching the filters."}{" "}
            Search matches the order ID or product name.
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:items-end">
          <label className="relative block sm:w-72">
            <span className="sr-only">Search orders</span>
            <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-subtle" />
            <input
              key={searchKey}
              type="search"
              defaultValue={query.search}
              onChange={(event) => search(event.target.value)}
              maxLength={100}
              placeholder="Search order ID or product…"
              className="h-9 w-full rounded-lg border border-line bg-white pl-9 pr-3 text-[13px] text-ink shadow-sm placeholder:text-ink-subtle hover:border-line-strong"
            />
          </label>
          <div className="flex gap-2 md:hidden">
            <div className="flex-1">
              <Select label="Sort orders by" value={query.sort} onChange={(value) => onSort(value as OrderSortField)}>
                {Object.entries(ORDER_SORT_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    Sort: {label}
                  </option>
                ))}
              </Select>
            </div>
            <button
              type="button"
              onClick={() => onSort(query.sort)}
              aria-label={query.order === "asc" ? "Sorted ascending, switch to descending" : "Sorted descending, switch to ascending"}
              className="grid size-9 shrink-0 place-items-center rounded-lg border border-line bg-white text-ink-muted shadow-sm hover:text-ink"
            >
              {query.order === "asc" ? <ArrowUpNarrowWide aria-hidden className="size-4" /> : <ArrowDownWideNarrow aria-hidden className="size-4" />}
            </button>
          </div>
        </div>
      </div>

      {page.total === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title="No orders match"
          description="Try a different search term, status, or fewer filters."
          action={
            <button type="button" onClick={onClear} className={secondary}>
              Clear filters
            </button>
          }
          className="border-t border-line py-14"
        />
      ) : page.items.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
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
          <DesktopTable rows={page.items} query={query} lateField={lateField} onSort={onSort} />
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
            itemLabel="orders"
          />
        </div>
      )}
    </motion.section>
  );
}

function SortHeader({
  field,
  label,
  align,
  query,
  onSort,
}: {
  field: OrderSortField;
  label: string;
  align?: "right";
  query: PurchaseOrderQuery;
  onSort: (field: OrderSortField) => void;
}) {
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

function DesktopTable({
  rows,
  query,
  lateField,
  onSort,
}: {
  rows: PurchaseOrder[];
  query: PurchaseOrderQuery;
  lateField: OrderSortField;
  onSort: (field: OrderSortField) => void;
}) {
  const header = { query, onSort };
  return (
    <div className="hidden overflow-x-auto md:block">
      <table className="w-full min-w-[1000px] text-left text-[13px]">
        <caption className="sr-only">Purchase orders. Column headers sort the table.</caption>
        <thead>
          <tr className="border-y border-line bg-slate-50/60 text-[11px] text-ink-subtle">
            <SortHeader field="purchase_order_id" label="Order" {...header} />
            <th scope="col" className="px-3 py-2 font-medium uppercase tracking-wide">Product</th>
            <th scope="col" className="px-3 py-2 font-medium uppercase tracking-wide">Status</th>
            <SortHeader field="order_date" label="Ordered" {...header} />
            <SortHeader field="expected_delivery_date" label="Promised" {...header} />
            <SortHeader field="actual_delivery_date" label="Delivered" {...header} />
            <SortHeader field={lateField} label={lateField === "days_late" ? "Days late" : "Lateness"} {...header} />
            <SortHeader field="quantity_ordered" label="Qty" align="right" {...header} />
            <SortHeader field="value" label="Value" align="right" {...header} />
          </tr>
        </thead>
        <tbody>
          {rows.map((po) => {
            const late = lateness(po);
            return (
              <tr key={po.purchase_order_id} className="border-b border-line transition-colors last:border-b-0 hover:bg-slate-50/70">
                <td className="px-3 py-2.5">
                  <p className="font-mono text-xs text-ink">{po.purchase_order_id}</p>
                  <p className="text-[11px] text-ink-subtle">{formatStore(po.store_id)}</p>
                </td>
                <td className="max-w-[260px] px-3 py-2.5">
                  <p className="truncate font-medium text-ink">{po.product_name}</p>
                  <p className="truncate text-xs text-ink-subtle">
                    {po.supplier_name} · {po.category}
                  </p>
                </td>
                <td className="px-3 py-2.5">
                  <PurchaseOrderBadge status={po.order_status} />
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 text-ink-muted">{formatShortDate(po.order_date)}</td>
                <td className="whitespace-nowrap px-3 py-2.5 text-ink-muted">{formatShortDate(po.expected_delivery_date)}</td>
                <td className="whitespace-nowrap px-3 py-2.5 text-ink-muted">
                  {po.actual_delivery_date ? formatShortDate(po.actual_delivery_date) : "—"}
                </td>
                <td className={cn("whitespace-nowrap px-3 py-2.5", late.tone)}>{late.text}</td>
                <td className="px-3 py-2.5 text-right tabular-nums text-ink-muted">{formatInteger(po.quantity_ordered)}</td>
                <td className="px-3 py-2.5 text-right font-medium tabular-nums text-ink">{formatCurrency(po.value)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function MobileList({ rows }: { rows: PurchaseOrder[] }) {
  return (
    <ul className="divide-y divide-line border-t border-line md:hidden">
      {rows.map((po) => {
        const late = lateness(po);
        return (
          <li key={po.purchase_order_id} className="px-4 py-3.5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-ink">{po.product_name}</p>
                <p className="truncate text-xs text-ink-subtle">
                  <span className="font-mono">{po.purchase_order_id}</span> · {formatStore(po.store_id)}
                </p>
              </div>
              <PurchaseOrderBadge status={po.order_status} />
            </div>
            <dl className="mt-3 grid grid-cols-3 gap-x-3 gap-y-2">
              {(
                [
                  ["Ordered", formatShortDate(po.order_date)],
                  ["Promised", formatShortDate(po.expected_delivery_date)],
                  ["Delivered", po.actual_delivery_date ? formatShortDate(po.actual_delivery_date) : "—"],
                  ["Qty", formatInteger(po.quantity_ordered)],
                  ["Value", formatCurrency(po.value)],
                  ["Supplier", po.supplier_name],
                ] as const
              ).map(([label, value]) => (
                <div key={label} className="min-w-0">
                  <dt className="truncate text-[11px] text-ink-subtle">{label}</dt>
                  <dd className="truncate text-[13px] font-medium tabular-nums text-ink">{value}</dd>
                </div>
              ))}
            </dl>
            <p className={cn("mt-2 text-xs", late.tone)}>{late.text}</p>
          </li>
        );
      })}
    </ul>
  );
}
