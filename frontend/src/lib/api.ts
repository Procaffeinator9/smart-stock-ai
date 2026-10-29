// Server-side helpers for calling the SmartStock FastAPI backend.
// API_BASE_URL has no NEXT_PUBLIC_ prefix, so it is only readable on the server and
// is never inlined into browser JavaScript. The frontend never holds Databricks credentials.

export type HealthResponse = {
  status: "ok";
  service: string;
  version: string;
  environment: string;
  databricks_configured: boolean;
  data_source: "csv" | "databricks";
};

export type HealthResult =
  | { ok: true; data: HealthResponse }
  | { ok: false; error: string };

const DEFAULT_API_BASE_URL = "http://localhost:8000";

function baseUrl(): string {
  return process.env.API_BASE_URL ?? DEFAULT_API_BASE_URL;
}

export async function fetchHealth(): Promise<HealthResult> {
  try {
    const response = await fetch(`${baseUrl()}/api/v1/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    if (!response.ok) {
      return { ok: false, error: `Backend responded with HTTP ${response.status}` };
    }
    return { ok: true, data: (await response.json()) as HealthResponse };
  } catch {
    return { ok: false, error: "Backend is unreachable" };
  }
}

export type ApiErrorKind = "unreachable" | "invalid" | "unavailable" | "error";

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; kind: ApiErrorKind; status?: number; message: string; retryAfterSeconds?: number };

/** Message from a FastAPI error body: a string, or a list of validation errors. */
function errorMessage(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (d as { msg?: string }).msg).filter(Boolean).join("; ") || null;
  }
  return null;
}

/** GET a read-only data endpoint from the server. Never throws. */
export async function apiGet<T>(path: string, params?: URLSearchParams): Promise<ApiResult<T>> {
  const url = `${baseUrl()}${path}${params && params.size ? `?${params}` : ""}`;
  let response: Response;
  try {
    response = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(15000) });
  } catch {
    return { ok: false, kind: "unreachable", message: "The data API is unreachable." };
  }
  if (response.ok) return { ok: true, data: (await response.json()) as T };

  const message = errorMessage(await response.json().catch(() => null)) ?? `HTTP ${response.status}`;
  const kind: ApiErrorKind = response.status === 422 ? "invalid" : response.status === 503 ? "unavailable" : "error";
  const retryAfter = Number.parseInt(response.headers.get("Retry-After") ?? "", 10);
  return {
    ok: false,
    kind,
    status: response.status,
    message,
    ...(Number.isFinite(retryAfter) && retryAfter > 0 ? { retryAfterSeconds: retryAfter } : {}),
  };
}
