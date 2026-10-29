"use client";

import { createContext, useContext } from "react";

import type { RangeId } from "@/lib/dashboard/date-range";

interface ShellContextValue {
  range: RangeId;
  setRange: (range: RangeId) => void;
  openSearch: () => void;
  openAbout: () => void;
}

export const ShellContext = createContext<ShellContextValue | null>(null);

export function useShell(): ShellContextValue {
  const value = useContext(ShellContext);
  if (!value) throw new Error("useShell must be used inside <AppShell>");
  return value;
}
