"use client";

import { ChevronDown, Info, Moon, Settings } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useId, useRef, useState } from "react";

import { cn } from "@/lib/cn";

import { useShell } from "./shell-context";

/** Disclosure-style menu. There is no sign-in in this phase, so the profile is a local demo user. */
export function ProfileMenu() {
  const [open, setOpen] = useState(false);
  const { openAbout } = useShell();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (!panelRef.current?.contains(target) && !buttonRef.current?.contains(target)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const itemClass =
    "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-medium text-ink transition-colors hover:bg-slate-100";

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-2 rounded-full py-1 pl-1 pr-2 transition-colors hover:bg-slate-100"
      >
        <span className="grid size-8 place-items-center rounded-full bg-gradient-to-br from-indigo-500 to-sky-500 text-[11px] font-semibold text-white ring-2 ring-white">
          DU
        </span>
        <span className="sr-only">Account menu</span>
        <ChevronDown aria-hidden className={cn("hidden size-4 text-ink-subtle transition-transform sm:block", open && "rotate-180")} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            ref={panelRef}
            id={panelId}
            initial={{ opacity: 0, scale: 0.96, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: -4 }}
            transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
            className="absolute right-0 top-full z-40 mt-2 w-64 origin-top-right rounded-xl border border-line bg-surface p-1.5 shadow-pop"
          >
            <div className="px-2.5 pb-2.5 pt-2">
              <p className="text-sm font-semibold text-ink">Demo user</p>
              <p className="text-xs text-ink-subtle">Local · synthetic workspace</p>
            </div>
            <div className="border-t border-line pt-1.5">
              <button
                type="button"
                className={itemClass}
                onClick={() => {
                  setOpen(false);
                  openAbout();
                }}
              >
                <Info aria-hidden className="size-4 text-ink-subtle" />
                About this data
              </button>
              <button type="button" disabled className={cn(itemClass, "cursor-not-allowed text-ink-subtle hover:bg-transparent")}>
                <Moon aria-hidden className="size-4" />
                Dark theme
                <span className="ml-auto text-[10px] font-semibold uppercase tracking-wide">Soon</span>
              </button>
              <button type="button" disabled className={cn(itemClass, "cursor-not-allowed text-ink-subtle hover:bg-transparent")}>
                <Settings aria-hidden className="size-4" />
                Account settings
                <span className="ml-auto text-[10px] font-semibold uppercase tracking-wide">Soon</span>
              </button>
            </div>
            <p className="mt-1.5 border-t border-line px-2.5 pb-1 pt-2 text-[11px] leading-4 text-ink-subtle">
              Sign-in is not part of this phase.
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
