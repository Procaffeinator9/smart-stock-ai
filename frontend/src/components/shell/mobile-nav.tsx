"use client";

import { X } from "lucide-react";
import { useId, type ReactNode } from "react";

import { Dialog } from "@/components/ui/dialog";

import { LogoMark, Wordmark } from "./logo";
import { NavList } from "./nav-list";

interface MobileNavProps {
  open: boolean;
  onClose: () => void;
  status: ReactNode;
}

export function MobileNav({ open, onClose, status }: MobileNavProps) {
  const titleId = useId();
  return (
    <Dialog open={open} onClose={onClose} labelledBy={titleId} placement="left" className="flex flex-col">
      <div className="flex h-16 items-center justify-between border-b border-line px-4">
        <div className="flex items-center gap-2.5">
          <LogoMark />
          <Wordmark />
          <span id={titleId} className="sr-only">
            Navigation
          </span>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close navigation"
          className="grid size-9 place-items-center rounded-lg text-ink-muted hover:bg-slate-100 hover:text-ink"
        >
          <X aria-hidden className="size-5" />
        </button>
      </div>
      <nav aria-label="Primary" className="flex-1 overflow-y-auto p-3">
        <NavList onNavigate={onClose} />
      </nav>
      <div className="border-t border-line p-4">{status}</div>
    </Dialog>
  );
}
