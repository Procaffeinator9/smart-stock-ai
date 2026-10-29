"use client";

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

import { LogoMark, Wordmark } from "./logo";
import { NavList } from "./nav-list";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  status: ReactNode;
}

export const SIDEBAR_WIDTH = { expanded: 272, collapsed: 76 };

export function Sidebar({ collapsed, onToggle, status }: SidebarProps) {
  return (
    <motion.aside
      initial={false}
      animate={{ width: collapsed ? SIDEBAR_WIDTH.collapsed : SIDEBAR_WIDTH.expanded }}
      transition={{ type: "spring", stiffness: 340, damping: 36 }}
      data-collapsed={collapsed}
      className="group/sidebar sticky top-0 z-30 hidden h-dvh shrink-0 flex-col overflow-hidden border-r border-line bg-white/75 backdrop-blur-xl lg:flex"
    >
      <div className={cn("flex h-16 items-center gap-2.5 px-[22px]")}>
        <Link href="/" className="flex items-center gap-2.5 rounded-lg" aria-label="SmartStock AI home">
          <LogoMark />
          <Wordmark className={cn("transition-opacity duration-200", collapsed && "pointer-events-none opacity-0")} />
        </Link>
      </div>

      <nav aria-label="Primary" className="flex-1 overflow-y-auto px-3 py-3">
        {!collapsed && (
          <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-subtle">Workspace</p>
        )}
        <NavList collapsed={collapsed} />
      </nav>

      <div className="space-y-2 border-t border-line p-3">
        <div className={cn("px-1", collapsed && "flex justify-center px-0")}>{status}</div>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "flex h-9 w-full items-center gap-2 rounded-lg px-3 text-[13px] font-medium text-ink-muted transition-colors hover:bg-slate-100 hover:text-ink",
            collapsed && "justify-center px-0",
          )}
        >
          {collapsed ? <PanelLeftOpen aria-hidden className="size-4" /> : <PanelLeftClose aria-hidden className="size-4" />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </motion.aside>
  );
}
