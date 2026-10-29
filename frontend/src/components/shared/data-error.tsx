"use client";

import { DatabaseZap, FilterX, Hourglass, RotateCw, ServerOff, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { cardClassName } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import type { ApiErrorKind } from "@/lib/api";

export type DataErrorKind = ApiErrorKind | "loading";

const COPY: Record<DataErrorKind, { icon: LucideIcon; title: string; hint?: string }> = {
  unreachable: {
    icon: ServerOff,
    title: "Can't reach the data API",
    hint: "Start the FastAPI backend: cd backend, then uvicorn app.main:app --reload",
  },
  unavailable: { icon: DatabaseZap, title: "The data source is unavailable" },
  invalid: { icon: FilterX, title: "These filters aren't valid" },
  error: { icon: ServerOff, title: "The data API returned an error" },
  loading: { icon: Hourglass, title: "Live data is still loading" },
};

interface DataErrorProps {
  kind: DataErrorKind;
  message: string;
  retryAfterSeconds?: number | null;
  /** Shown instead of "Try again" (e.g. resetting invalid filters). */
  resetHref?: string;
  resetLabel?: string;
  hint?: string;
}

/** Error / not-ready state for data pages. Retrying is always manual: there is no polling. */
export function DataError({ kind, message, retryAfterSeconds, resetHref, resetLabel = "Reset filters", hint }: DataErrorProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const copy = COPY[kind];
  const footnote = hint ?? copy.hint;
  const button =
    "inline-flex items-center gap-2 rounded-lg bg-brand px-3.5 py-2 text-sm font-medium text-white shadow-sm hover:bg-brand-strong disabled:opacity-60";

  return (
    <div className={cardClassName} role="alert">
      <EmptyState
        icon={copy.icon}
        tone={kind === "loading" ? "neutral" : "danger"}
        title={copy.title}
        description={
          <>
            {kind === "loading" && retryAfterSeconds
              ? `The data source is loading its first snapshot. Try again in about ${retryAfterSeconds} s.`
              : message}
            {footnote && <span className="mt-2 block font-mono text-xs text-ink-subtle">{footnote}</span>}
          </>
        }
        action={
          resetHref ? (
            <Link href={resetHref} className={button}>
              <FilterX aria-hidden className="size-4" /> {resetLabel}
            </Link>
          ) : (
            <button type="button" disabled={isPending} onClick={() => startTransition(() => router.refresh())} className={button}>
              <RotateCw aria-hidden className={isPending ? "size-4 animate-spin" : "size-4"} />
              {isPending ? "Retrying…" : "Try again"}
            </button>
          )
        }
        className="py-16"
      />
    </div>
  );
}
