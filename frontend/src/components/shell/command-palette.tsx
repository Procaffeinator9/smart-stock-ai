"use client";

import { ArrowLeft, CornerDownLeft, Package, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useRef, useState, type KeyboardEvent } from "react";

import { Dialog } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import type { ProductIndexEntry, SnapshotMeta } from "@/lib/dashboard/types";
import { formatCurrencyPrecise, formatInteger, formatLongDate } from "@/lib/format";

import { NAV_ITEMS, type NavItem } from "./nav-config";

const MAX_PRODUCTS = 8;

type Result =
  | { kind: "page"; id: string; item: NavItem; disabled: boolean }
  | { kind: "product"; id: string; product: ProductIndexEntry; disabled: false };

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  products: ProductIndexEntry[];
  meta: SnapshotMeta;
}

export function CommandPalette({ open, onClose, products, meta }: CommandPaletteProps) {
  const titleId = useId();
  return (
    <Dialog open={open} onClose={onClose} labelledBy={titleId} placement="top" className="overflow-hidden">
      <h2 id={titleId} className="sr-only">
        Search
      </h2>
      {/* Mounted only while open, so state resets each time. */}
      <PaletteBody products={products} meta={meta} onClose={onClose} />
    </Dialog>
  );
}

function PaletteBody({ products, meta, onClose }: Omit<CommandPaletteProps, "open">) {
  const router = useRouter();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [selected, setSelected] = useState<ProductIndexEntry | null>(null);

  const q = query.trim().toLowerCase();
  const pages: Result[] = NAV_ITEMS.filter((item) => !q || item.label.toLowerCase().includes(q)).map((item) => ({
    kind: "page",
    id: `page-${item.label}`,
    item,
    disabled: !item.href,
  }));
  const productResults: Result[] = q
    ? products
        .filter((p) =>
          [p.product_name, p.sku, p.product_id, p.category, p.supplier_name].some((field) => field.toLowerCase().includes(q)),
        )
        .slice(0, MAX_PRODUCTS)
        .map((product) => ({ kind: "product", id: `product-${product.product_id}`, product, disabled: false }))
    : [];
  const results = [...productResults, ...pages];
  const enabled = results.filter((r) => !r.disabled);
  const activeResult = enabled[Math.min(active, enabled.length - 1)];

  function choose(result: Result) {
    if (result.disabled) return;
    if (result.kind === "product") {
      setSelected(result.product);
      return;
    }
    onClose();
    router.push(result.item.href!);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!enabled.length) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((index) => (Math.min(index, enabled.length - 1) + step + enabled.length) % enabled.length);
    } else if (event.key === "Enter" && activeResult) {
      event.preventDefault();
      choose(activeResult);
    }
  }

  if (selected) {
    return (
      <ProductDetail
        product={selected}
        asOf={meta.as_of}
        onOpenInventory={() => {
          onClose();
          router.push(`/inventory?search=${encodeURIComponent(selected.product_id)}`);
        }}
        onBack={() => {
          setSelected(null);
          requestAnimationFrame(() => inputRef.current?.focus());
        }}
      />
    );
  }

  const optionClass = (result: Result) =>
    cn(
      "flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm",
      result.disabled && "cursor-not-allowed text-ink-subtle",
      !result.disabled && result.id === activeResult?.id && "bg-brand-soft text-brand-strong",
    );

  return (
    <div>
      <div className="flex items-center gap-3 border-b border-line px-4">
        <Search aria-hidden className="size-4 shrink-0 text-ink-subtle" />
        <input
          ref={inputRef}
          autoFocus
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActive(0);
          }}
          onKeyDown={onKeyDown}
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={activeResult ? `${listId}-${activeResult.id}` : undefined}
          placeholder={`Search ${products.length} products by name, SKU, category or supplier…`}
          className="h-14 w-full bg-transparent text-[15px] text-ink outline-none placeholder:text-ink-subtle"
        />
      </div>

      <ul id={listId} role="listbox" aria-label="Results" className="max-h-[min(60vh,26rem)] overflow-y-auto p-2">
        {q && productResults.length === 0 && (
          <li role="presentation" className="px-3 py-6 text-center text-sm text-ink-muted">
            No products match “{query.trim()}”.
          </li>
        )}
        {productResults.length > 0 && <GroupLabel>Products</GroupLabel>}
        {productResults.map((result) =>
          result.kind === "product" ? (
            <li
              key={result.id}
              id={`${listId}-${result.id}`}
              role="option"
              aria-selected={result.id === activeResult?.id}
              onClick={() => choose(result)}
              onMouseMove={() => setActive(enabled.indexOf(result))}
              className={optionClass(result)}
            >
              <Package aria-hidden className="size-4 shrink-0 text-ink-subtle" />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-ink">{result.product.product_name}</span>
                <span className="block truncate text-xs text-ink-subtle">
                  {result.product.sku} · {result.product.category}
                </span>
              </span>
              <StatusBadge status={result.product.status} />
            </li>
          ) : null,
        )}
        {pages.length > 0 && <GroupLabel>Pages</GroupLabel>}
        {pages.map((result) =>
          result.kind === "page" ? (
            <li
              key={result.id}
              id={`${listId}-${result.id}`}
              role="option"
              aria-selected={result.id === activeResult?.id}
              aria-disabled={result.disabled}
              onClick={() => choose(result)}
              onMouseMove={() => !result.disabled && setActive(enabled.indexOf(result))}
              className={optionClass(result)}
            >
              <result.item.icon aria-hidden className="size-4 shrink-0" />
              <span className="flex-1 truncate">{result.item.label}</span>
              {result.disabled && <span className="text-[10px] font-semibold uppercase tracking-wide">Soon</span>}
            </li>
          ) : null,
        )}
      </ul>

      <div className="flex items-center gap-4 border-t border-line bg-slate-50/70 px-4 py-2.5 text-[11px] text-ink-subtle">
        <span>
          <Kbd>↑</Kbd> <Kbd>↓</Kbd> navigate
        </span>
        <span>
          <Kbd>↵</Kbd> select
        </span>
        <span>
          <Kbd>Esc</Kbd> close
        </span>
        <span className="ml-auto hidden sm:inline">Synthetic data · as of {formatLongDate(meta.as_of)}</span>
      </div>
    </div>
  );
}

function GroupLabel({ children }: { children: string }) {
  return (
    <li role="presentation" className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-subtle">
      {children}
    </li>
  );
}

function Kbd({ children }: { children: string }) {
  return <kbd className="rounded border border-line bg-white px-1 py-px font-sans font-medium text-ink-muted">{children}</kbd>;
}

function ProductDetail({
  product,
  asOf,
  onBack,
  onOpenInventory,
}: {
  product: ProductIndexEntry;
  asOf: string;
  onBack: () => void;
  onOpenInventory: () => void;
}) {
  const facts: Array<[string, string]> = [
    ["Category", product.category],
    ["Supplier", product.supplier_name],
    ["Selling price", formatCurrencyPrecise(product.selling_price)],
    ["On hand (all stores)", formatInteger(product.on_hand)],
    ["Available (all stores)", formatInteger(product.available)],
    ["Stores at stockout risk", String(product.stores_at_risk)],
  ];
  return (
    <div className="p-5">
      <button
        type="button"
        autoFocus
        onClick={onBack}
        className="mb-4 inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-ink-muted hover:bg-slate-100 hover:text-ink"
      >
        <ArrowLeft aria-hidden className="size-3.5" /> Back to results
      </button>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-lg font-semibold tracking-tight text-ink">{product.product_name}</p>
          <p className="text-xs text-ink-subtle">
            {product.sku} · {product.product_id}
          </p>
        </div>
        <StatusBadge status={product.status} />
      </div>
      <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
        {facts.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-ink-subtle">{label}</dt>
            <dd className="font-medium tabular-nums text-ink">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-5 rounded-lg bg-slate-50 px-3 py-2 text-xs text-ink-muted">
        Status is the worst across stores, as of {formatLongDate(asOf)} (synthetic data).
      </p>
      <button
        type="button"
        onClick={onOpenInventory}
        className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-brand px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-brand-strong"
      >
        View stock by store in Inventory
        <CornerDownLeft aria-hidden className="size-3.5" />
      </button>
    </div>
  );
}
