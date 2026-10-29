import type { CSSProperties } from "react";

import { cn } from "@/lib/cn";

export function Skeleton({ className, style }: { className?: string; style?: CSSProperties }) {
  return <div aria-hidden className={cn("animate-pulse rounded-lg bg-slate-200/60", className)} style={style} />;
}
