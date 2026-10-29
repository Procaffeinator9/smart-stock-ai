// Pure helpers for presenting live (API-backed) dashboard data: failure classification,
// freshness wording, and dataset "as of" vs today's date. No runtime imports, so the
// tests in frontend/tests can load this file directly with Node's built-in test runner.
import type { ApiErrorKind } from "@/lib/api";
import type { DataFreshness, DataSourceName } from "@/lib/dashboard/types";

export type FailureView =
  | { kind: "loading"; message: string; retryAfterSeconds: number | null }
  | { kind: ApiErrorKind; message: string; retryAfterSeconds: number | null };

/** A 503 while the first snapshot loads is shown as "loading", not as an outage. */
export function classifyFailure(kind: ApiErrorKind, message: string, retryAfterSeconds?: number): FailureView {
  const retry = retryAfterSeconds && retryAfterSeconds > 0 ? retryAfterSeconds : null;
  if (kind === "unavailable" && /still loading/i.test(message)) {
    return { kind: "loading", message, retryAfterSeconds: retry };
  }
  return { kind, message, retryAfterSeconds: retry };
}

export function sourceLabel(source: DataSourceName): string {
  if (source === "databricks") return "Databricks";
  if (source === "csv") return "Local CSV files";
  return "Static snapshot";
}

/** "under a minute", "12 min", "5 h", "3 days". */
export function formatAge(seconds: number): string {
  if (seconds < 60) return "under a minute";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)} h`;
  const days = Math.floor(seconds / 86_400);
  return `${days} day${days === 1 ? "" : "s"}`;
}

export interface FreshnessView {
  tone: "fresh" | "stale" | "failed" | "unknown";
  /** Short status, e.g. "Loaded 12 min ago". */
  summary: string;
  /** Extra warning text for stale or failed states. */
  warning: string | null;
}

export function describeFreshness(freshness: DataFreshness): FreshnessView {
  const age = freshness.age_seconds;
  if (freshness.loaded_at === null || age === null) {
    return { tone: "unknown", summary: "Load time unknown", warning: null };
  }
  const summary = `Loaded ${formatAge(age)} ago`;
  if (freshness.last_error) {
    return {
      tone: "failed",
      summary,
      warning: `The latest refresh failed (${freshness.last_error}). Showing the last good snapshot, ${formatAge(age)} old.`,
    };
  }
  if (freshness.stale) {
    return {
      tone: "stale",
      summary,
      warning: `This snapshot is past its refresh interval${freshness.refreshing ? "; a refresh is in progress" : ""}.`,
    };
  }
  return { tone: "fresh", summary, warning: null };
}

const DAY_MS = 86_400_000;

/** YYYY-MM-DD of an instant in a time zone (default: the runtime's zone). */
export function isoDay(instant: Date, timeZone?: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone }).formatToParts(instant);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

function dayLabel(isoDate: string): string {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(
    new Date(`${isoDate}T00:00:00Z`),
  );
}

export interface DatasetDates {
  asOfLabel: string;
  todayIso: string;
  todayLabel: string;
  /** Whole days from the dataset's as_of date to today (0 when current or in the future). */
  daysBehind: number;
}

/** The data's as_of date and today's date, kept separate so one is never mistaken for the other. */
export function datasetDates(asOfIso: string, now: Date, timeZone?: string): DatasetDates {
  const todayIso = isoDay(now, timeZone);
  const behind = Math.round((Date.parse(`${todayIso}T00:00:00Z`) - Date.parse(`${asOfIso}T00:00:00Z`)) / DAY_MS);
  return { asOfLabel: dayLabel(asOfIso), todayIso, todayLabel: dayLabel(todayIso), daysBehind: Math.max(behind, 0) };
}
