import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
  tone?: "neutral" | "danger";
}

export function EmptyState({ icon: Icon, title, description, action, className, tone = "neutral" }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-10 text-center", className)}>
      <span
        className={cn(
          "mb-3 grid size-11 place-items-center rounded-xl ring-1 ring-inset",
          tone === "danger" ? "bg-red-50 text-red-600 ring-red-600/15" : "bg-slate-50 text-ink-subtle ring-line",
        )}
      >
        <Icon aria-hidden className="size-5" />
      </span>
      <p className="text-sm font-semibold text-ink">{title}</p>
      {description && <p className="mt-1 max-w-sm text-[13px] leading-5 text-ink-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
