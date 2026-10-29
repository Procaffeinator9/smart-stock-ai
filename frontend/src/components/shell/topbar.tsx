"use client";

import { Menu, Search } from "lucide-react";
import { usePathname } from "next/navigation";
import { Suspense, useSyncExternalStore, type ReactNode } from "react";

import { DateRangeControl } from "./date-range-control";
import { pageTitle } from "./nav-config";
import { ProfileMenu } from "./profile-menu";
import { useShell } from "./shell-context";

const noopSubscribe = () => () => {};

/** "⌘" on Apple platforms, "Ctrl" elsewhere (and during server rendering). */
function useShortcutModifier(): string {
  return useSyncExternalStore(
    noopSubscribe,
    () => (/Mac|iPhone|iPad/.test(navigator.userAgent) ? "⌘" : "Ctrl"),
    () => "Ctrl",
  );
}

interface TopbarProps {
  onOpenMenu: () => void;
}

// The pathname is unknown while prerendering a page with a dynamic segment (e.g. /suppliers/[id]),
// so the parts that read it render inside Suspense. Static routes resolve it during prerendering.
function PageTitle() {
  return <>{pageTitle(usePathname())}</>;
}

/** Only the overview uses the date range. */
function OverviewOnly({ children }: { children: ReactNode }) {
  return usePathname() === "/" ? children : null;
}

export function Topbar({ onOpenMenu }: TopbarProps) {
  const { openSearch } = useShell();
  const modifier = useShortcutModifier();

  return (
    <header className="sticky top-0 z-20 border-b border-line/80 bg-canvas/80 backdrop-blur-xl">
      <div className="flex h-16 items-center gap-3 px-4 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={onOpenMenu}
          aria-label="Open navigation"
          className="-ml-1 grid size-9 place-items-center rounded-lg text-ink-muted hover:bg-slate-100 hover:text-ink lg:hidden"
        >
          <Menu aria-hidden className="size-5" />
        </button>

        <div className="min-w-0 flex-1">
          <h1 className="truncate text-lg font-semibold tracking-tight text-ink">
            <Suspense fallback={<span className="invisible">SmartStock AI</span>}>
              <PageTitle />
            </Suspense>
          </h1>
          <p className="hidden truncate text-xs text-ink-subtle sm:block">
            Synthetic retail dataset · read-only
          </p>
        </div>

        <button
          type="button"
          onClick={openSearch}
          aria-label="Search products and pages"
          aria-keyshortcuts="Control+K Meta+K"
          className="group flex h-9 items-center gap-2 rounded-lg border border-line bg-white/80 px-2.5 text-[13px] text-ink-subtle shadow-sm transition-colors hover:border-line-strong hover:text-ink-muted md:w-64"
        >
          <Search aria-hidden className="size-4" />
          <span className="hidden md:inline">Search products, SKUs…</span>
          <kbd className="ml-auto hidden rounded border border-line bg-slate-50 px-1.5 py-px font-sans text-[11px] font-medium text-ink-subtle md:inline">
            {modifier} K
          </kbd>
        </button>

        <Suspense fallback={null}>
          <OverviewOnly>
            <DateRangeControl className="hidden sm:flex" />
          </OverviewOnly>
        </Suspense>
        <ProfileMenu />
      </div>

      <Suspense fallback={null}>
        <OverviewOnly>
          <div className="flex items-center justify-between gap-3 border-t border-line/70 px-4 py-2 sm:hidden">
            <span className="text-xs text-ink-subtle">Date range</span>
            <DateRangeControl />
          </div>
        </OverviewOnly>
      </Suspense>
    </header>
  );
}
