"use client";

import { ArrowDown, ArrowUp, ArrowUpDown, ChevronRight } from "lucide-react";
import { Fragment, useState } from "react";

import { PurchaseOrderBadge, StatusBadge } from "@/components/ui/status-badge";
import { StockMeter } from "@/components/ui/stock-meter";
import { cn } from "@/lib/cn";
import type { SortField, SortOrder } from "@/lib/inventory/query";
import type { InventoryPosition } from "@/lib/inventory/types";
import { formatInteger, formatShortDate, formatStore } from "@/lib/format";

import { coverLabel, deliveryLabel } from "./inventory-format";

const keyOf = (p: InventoryPosition) => `${p.store_id}|${p.product_id}`;
const needsReorder = (p: InventoryPosition) => p.inventory_position <= p.reorder_point;

interface InventoryTableProps {
  rows: InventoryPosition[];
  asOf: string;
  sort: SortField;
  order: SortOrder;
  onSort: (sort: SortField) => void;
}

export function InventoryTable({ rows, asOf, sort, order, onSort }: InventoryTableProps) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const toggle = (key: string) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <>
      <DesktopTable rows={rows} asOf={asOf} sort={sort} order={order} onSort={onSort} expanded={expanded} onToggle={toggle} />
      <MobileList rows={rows} asOf={asOf} expanded={expanded} onToggle={toggle} />
    </>
  );
}

function SortHeader({
  field,
  label,
  sort,
  order,
  onSort,
  align = "left",
}: {
  field: SortField;
  label: string;
  sort: SortField;
  order: SortOrder;
  onSort: (sort: SortField) => void;
  align?: "left" | "right";
}) {
  const active = sort === field;
  const Icon = !active ? ArrowUpDown : order === "asc" ? ArrowUp : ArrowDown;
  return (
    <th
      scope="col"
      aria-sort={active ? (order === "asc" ? "ascending" : "descending") : "none"}
      className={cn("px-3 py-2 font-medium", align === "right" && "text-right")}
    >
      <button
        type="button"
        onClick={() => onSort(field)}
        className={cn(
          "inline-flex items-center gap-1 rounded uppercase tracking-wide hover:text-ink",
          active && "text-ink",
          align === "right" && "flex-row-reverse",
        )}
      >
        {label}
        <Icon aria-hidden className={cn("size-3", !active && "opacity-40")} />
      </button>
    </th>
  );
}

interface ListProps {
  rows: InventoryPosition[];
  asOf: string;
  expanded: Set<string>;
  onToggle: (key: string) => void;
}

function DesktopTable({ rows, asOf, sort, order, onSort, expanded, onToggle }: ListProps & Omit<InventoryTableProps, "rows" | "asOf">) {
  const header = { sort, order, onSort };
  return (
    <div className="hidden overflow-x-auto md:block">
      <table className="w-full min-w-[960px] text-left text-[13px]">
        <caption className="sr-only">Inventory positions by store and product. Column headers sort the table.</caption>
        <thead>
          <tr className="border-y border-line bg-slate-50/60 text-[11px] text-ink-subtle">
            <th scope="col" className="w-10 px-3 py-2">
              <span className="sr-only">Open purchase orders</span>
            </th>
            <SortHeader field="product_name" label="Product" {...header} />
            <SortHeader field="store_id" label="Store" {...header} />
            <SortHeader field="severity" label="Status" {...header} />
            <SortHeader field="available" label="Available" {...header} align="right" />
            <SortHeader field="reorder_point" label="Reorder pt" {...header} align="right" />
            <SortHeader field="safety_stock" label="Safety" {...header} align="right" />
            <SortHeader field="days_of_cover" label="Cover" {...header} align="right" />
            <SortHeader field="inventory_position" label="On order" {...header} align="right" />
            <SortHeader field="next_delivery" label="Next delivery" {...header} />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = keyOf(row);
            const isOpen = expanded.has(key);
            const delivery = deliveryLabel(row.next_delivery, asOf);
            const detailId = `po-${key}`;
            return (
              <Fragment key={key}>
                <tr className={cn("border-b border-line transition-colors hover:bg-slate-50/70", isOpen && "bg-slate-50/70")}>
                  <td className="px-3 py-2.5">
                    <button
                      type="button"
                      onClick={() => onToggle(key)}
                      aria-expanded={isOpen}
                      aria-controls={detailId}
                      aria-label={`Open purchase orders for ${row.product_name} at ${formatStore(row.store_id)}`}
                      className="grid size-7 place-items-center rounded-md text-ink-subtle hover:bg-slate-200/60 hover:text-ink"
                    >
                      <ChevronRight aria-hidden className={cn("size-4 transition-transform", isOpen && "rotate-90")} />
                    </button>
                  </td>
                  <td className="max-w-[260px] px-3 py-2.5">
                    <p className="truncate font-medium text-ink">{row.product_name}</p>
                    <p className="truncate text-xs text-ink-subtle">
                      {row.sku} · {row.category}
                    </p>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-ink-muted">{formatStore(row.store_id)}</td>
                  <td className="px-3 py-2.5">
                    <StatusBadge status={row.status} />
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <p className="font-semibold tabular-nums text-ink">{formatInteger(row.available)}</p>
                    <StockMeter
                      available={row.available}
                      reorderPoint={row.reorder_point}
                      safetyStock={row.safety_stock}
                      status={row.status}
                      className="ml-auto mt-1 w-16"
                    />
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-ink-muted">{formatInteger(row.reorder_point)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-ink-muted">{formatInteger(row.safety_stock)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-ink-muted" title={row.days_of_cover === null ? "No sales in the last 14 days" : undefined}>
                    {coverLabel(row.days_of_cover)}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <p className="tabular-nums text-ink">{row.open_po_quantity ? formatInteger(row.open_po_quantity) : "—"}</p>
                    {needsReorder(row) ? (
                      <p className="text-[11px] font-medium text-amber-700">Needs reorder</p>
                    ) : (
                      <p className="text-[11px] text-ink-subtle">{row.open_po_count} PO{row.open_po_count === 1 ? "" : "s"}</p>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5">
                    {delivery ? <span className={cn("font-medium", delivery.tone)}>{delivery.text}</span> : <span className="text-ink-subtle">—</span>}
                  </td>
                </tr>
                {isOpen && (
                  <tr id={detailId} className="border-b border-line bg-slate-50/70">
                    <td />
                    <td colSpan={9} className="px-3 pb-4 pt-1">
                      <OpenOrders row={row} asOf={asOf} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function MobileList({ rows, asOf, expanded, onToggle }: ListProps) {
  return (
    <ul className="divide-y divide-line border-t border-line md:hidden">
      {rows.map((row) => {
        const key = keyOf(row);
        const isOpen = expanded.has(key);
        const delivery = deliveryLabel(row.next_delivery, asOf);
        const facts: Array<[string, string]> = [
          ["Available", formatInteger(row.available)],
          ["Reorder pt", formatInteger(row.reorder_point)],
          ["Safety", formatInteger(row.safety_stock)],
          ["Cover", coverLabel(row.days_of_cover)],
          ["On order", row.open_po_quantity ? formatInteger(row.open_po_quantity) : "—"],
          ["Next delivery", delivery?.text ?? "—"],
        ];
        return (
          <li key={key} className="px-4 py-3.5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-ink">{row.product_name}</p>
                <p className="truncate text-xs text-ink-subtle">
                  {formatStore(row.store_id)} · {row.sku}
                </p>
              </div>
              <StatusBadge status={row.status} />
            </div>
            <dl className="mt-3 grid grid-cols-3 gap-x-3 gap-y-2">
              {facts.map(([label, value]) => (
                <div key={label} className="min-w-0">
                  <dt className="truncate text-[11px] text-ink-subtle">{label}</dt>
                  <dd className="truncate text-[13px] font-medium tabular-nums text-ink">{value}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-2.5 flex items-center justify-between gap-3">
              {needsReorder(row) ? <span className="text-xs font-medium text-amber-700">Needs reorder</span> : <span />}
              <button
                type="button"
                onClick={() => onToggle(key)}
                aria-expanded={isOpen}
                className="inline-flex items-center gap-1 text-xs font-medium text-brand hover:text-brand-strong"
              >
                {isOpen ? "Hide" : "Show"} open POs ({row.open_po_count})
                <ChevronRight aria-hidden className={cn("size-3.5 transition-transform", isOpen && "rotate-90")} />
              </button>
            </div>
            {isOpen && (
              <div className="mt-3">
                <OpenOrders row={row} asOf={asOf} />
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function OpenOrders({ row, asOf }: { row: InventoryPosition; asOf: string }) {
  return (
    <div className="rounded-xl border border-line bg-white p-3">
      <p className="mb-2 text-xs text-ink-muted">
        Inventory position{" "}
        <span className="font-semibold tabular-nums text-ink">{formatInteger(row.inventory_position)}</span> = available{" "}
        {formatInteger(row.available)} + on order {formatInteger(row.open_po_quantity)} · reorder point{" "}
        {formatInteger(row.reorder_point)} · supplier {row.supplier_name}
        {row.avg_daily_units > 0 && <> · selling {row.avg_daily_units.toFixed(1)}/day (last 14 days)</>}
      </p>
      {row.open_purchase_orders.length === 0 ? (
        <p className="text-xs text-ink-subtle">
          No open purchase orders as of {formatShortDate(asOf)}.
          {needsReorder(row) && " The position is at or below its reorder point."}
        </p>
      ) : (
        <ul className="divide-y divide-line">
          {row.open_purchase_orders.map((po) => {
            const delivery = deliveryLabel(po.expected_delivery_date, asOf);
            return (
              <li key={po.purchase_order_id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2 text-xs">
                <span className="font-mono text-ink">{po.purchase_order_id}</span>
                <span className="tabular-nums text-ink">{formatInteger(po.quantity)} units</span>
                <span className="text-ink-subtle">ordered {formatShortDate(po.order_date)}</span>
                <span className={cn("font-medium", delivery?.tone)}>
                  expected {formatShortDate(po.expected_delivery_date)}
                  {po.is_overdue && ` · ${delivery?.text}`}
                </span>
                <PurchaseOrderBadge status={po.status} className="ml-auto" />
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
