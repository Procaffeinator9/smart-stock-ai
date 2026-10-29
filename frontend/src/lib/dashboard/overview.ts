// Server-side access to GET /api/v1/overview. React's cache() deduplicates calls within one
// request, so a page view makes at most one overview request however many components ask.
import { cache } from "react";

import { apiGet, type ApiResult } from "@/lib/api";

import type { OverviewResponse } from "./types";

export const fetchOverview = cache(
  (): Promise<ApiResult<OverviewResponse>> => apiGet<OverviewResponse>("/api/v1/overview"),
);
