import { connection } from "next/server";

import { cn } from "@/lib/cn";
import { fetchHealth } from "@/lib/api";

type PillState = "checking" | "online" | "offline";

const DOT: Record<PillState, string> = {
  checking: "bg-slate-300",
  online: "bg-emerald-500",
  offline: "bg-red-500",
};

/** Compact API status. Text hides when the desktop sidebar is collapsed (data-collapsed on the sidebar). */
export function StatusPill({ state, label, detail }: { state: PillState; label: string; detail?: string }) {
  return (
    <div title={detail ?? label} className="flex min-w-0 items-center gap-2 text-xs text-ink-muted" role="status">
      <span className="relative flex size-2 shrink-0">
        {state === "online" && (
          <span className="absolute inline-flex size-full rounded-full bg-emerald-400 opacity-60 motion-safe:animate-ping [animation-iteration-count:3]" />
        )}
        <span className={cn("relative inline-flex size-2 rounded-full", DOT[state])} />
      </span>
      <span className="truncate group-data-[collapsed=true]/sidebar:sr-only">{label}</span>
    </div>
  );
}

/** Server component: checks the FastAPI health endpoint at request time (wrap in <Suspense>). */
export async function BackendStatus() {
  await connection();
  const health = await fetchHealth();
  if (!health.ok) {
    return <StatusPill state="offline" label="API offline" detail={`${health.error}. Start the FastAPI backend on port 8000.`} />;
  }
  const databricks = health.data.databricks_configured
    ? "Databricks credentials set (connection not checked)"
    : "Databricks not configured";
  return (
    <StatusPill
      state="online"
      label={`API online · v${health.data.version}`}
      detail={`${health.data.service} (${health.data.environment}). ${databricks}.`}
    />
  );
}
