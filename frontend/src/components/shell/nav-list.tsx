"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";

import { cn } from "@/lib/cn";

import { NAV_ITEMS, navItemFor } from "./nav-config";

interface NavListProps {
  collapsed?: boolean;
  onNavigate?: () => void;
}

/**
 * The pathname is unknown while prerendering a page with a dynamic segment (e.g. /suppliers/[id]),
 * so the active highlight is read inside Suspense; the fallback is the same list without it.
 */
export function NavList(props: NavListProps) {
  return (
    <Suspense fallback={<NavItems {...props} pathname={null} />}>
      <CurrentNavItems {...props} />
    </Suspense>
  );
}

function CurrentNavItems(props: NavListProps) {
  return <NavItems {...props} pathname={usePathname()} />;
}

function NavItems({ collapsed = false, onNavigate, pathname }: NavListProps & { pathname: string | null }) {
  const current = pathname === null ? undefined : navItemFor(pathname);

  return (
    <ul className="space-y-0.5">
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const active = current === item;
        const base = cn(
          "relative isolate flex h-10 items-center gap-3 rounded-xl px-3 text-sm font-medium",
          collapsed && "justify-center px-0",
        );

        if (!item.href) {
          return (
            <li key={item.label}>
              <span
                aria-disabled="true"
                title={`${item.label}: planned for a later phase`}
                className={cn(base, "cursor-not-allowed text-ink-subtle/80")}
              >
                <Icon aria-hidden className="size-[18px] shrink-0" strokeWidth={1.9} />
                {collapsed ? (
                  <span className="sr-only">{item.label} (coming soon)</span>
                ) : (
                  <>
                    <span className="truncate">{item.label}</span>
                    <span className="ml-auto rounded-full bg-slate-100 px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-ink-subtle">
                      Soon
                    </span>
                  </>
                )}
              </span>
            </li>
          );
        }

        return (
          <li key={item.label}>
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              title={collapsed ? item.label : undefined}
              className={cn(
                base,
                "transition-colors",
                active ? "text-brand-strong" : "text-ink-muted hover:bg-slate-100/80 hover:text-ink",
              )}
            >
              {active && (
                <motion.span
                  layoutId="nav-active"
                  className="absolute inset-0 -z-10 rounded-xl bg-brand-soft ring-1 ring-inset ring-brand/10"
                  transition={{ type: "spring", bounce: 0.15, duration: 0.45 }}
                />
              )}
              <Icon aria-hidden className="size-[18px] shrink-0" strokeWidth={active ? 2.2 : 1.9} />
              {collapsed ? <span className="sr-only">{item.label}</span> : <span className="truncate">{item.label}</span>}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
