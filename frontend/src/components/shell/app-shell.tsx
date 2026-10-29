"use client";

import { MotionConfig } from "motion/react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { DEFAULT_RANGE, type RangeId } from "@/lib/dashboard/date-range";
import type { ProductIndexEntry, SnapshotMeta } from "@/lib/dashboard/types";

import { AboutDataDialog } from "./about-data-dialog";
import { CommandPalette } from "./command-palette";
import { MobileNav } from "./mobile-nav";
import { ShellContext } from "./shell-context";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

interface AppShellProps {
  meta: SnapshotMeta;
  products: ProductIndexEntry[];
  /** Server-rendered API status, streamed in via <Suspense>. */
  status: ReactNode;
  children: ReactNode;
}

export function AppShell({ meta, products, status, children }: AppShellProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [range, setRange] = useState<RangeId>(DEFAULT_RANGE);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const shell = useMemo(
    () => ({ range, setRange, openSearch: () => setSearchOpen(true), openAbout: () => setAboutOpen(true) }),
    [range],
  );

  return (
    <ShellContext value={shell}>
      {/* Honour the OS "reduce motion" setting for every Motion animation. */}
      <MotionConfig reducedMotion="user">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-white focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:shadow-pop"
        >
          Skip to content
        </a>
        <div className="flex min-h-dvh">
          <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((value) => !value)} status={status} />
          <div className="flex min-w-0 flex-1 flex-col">
            <Topbar onOpenMenu={() => setMobileOpen(true)} />
            <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6 outline-none sm:px-6 lg:px-8">
              {children}
            </main>
          </div>
        </div>
        <MobileNav open={mobileOpen} onClose={() => setMobileOpen(false)} status={status} />
        <CommandPalette open={searchOpen} onClose={() => setSearchOpen(false)} products={products} meta={meta} />
        <AboutDataDialog open={aboutOpen} onClose={() => setAboutOpen(false)} meta={meta} />
      </MotionConfig>
    </ShellContext>
  );
}
