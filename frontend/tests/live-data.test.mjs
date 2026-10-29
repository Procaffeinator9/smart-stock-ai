// Run with: npm test (Node 24's built-in test runner; it loads the TypeScript module directly).
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  classifyFailure,
  datasetDates,
  describeFreshness,
  formatAge,
  isoDay,
  sourceLabel,
} from "../src/lib/dashboard/live-data.ts";

const fresh = {
  source: "databricks",
  loaded_at: "2026-10-27T09:00:00Z",
  age_seconds: 720,
  stale: false,
  refreshing: false,
  last_error: null,
  last_error_at: null,
  next_retry_in_seconds: null,
};

test("a 503 while the first snapshot loads is classified as loading, with Retry-After", () => {
  assert.deepEqual(classifyFailure("unavailable", "Databricks data is still loading. Try again shortly.", 10), {
    kind: "loading",
    message: "Databricks data is still loading. Try again shortly.",
    retryAfterSeconds: 10,
  });
});

test("other failures keep their kind; a missing or zero Retry-After becomes null", () => {
  assert.equal(classifyFailure("unavailable", "Databricks could not be reached.", 15).kind, "unavailable");
  assert.equal(classifyFailure("unreachable", "The data API is unreachable.").kind, "unreachable");
  assert.equal(classifyFailure("unreachable", "x").retryAfterSeconds, null);
  assert.equal(classifyFailure("unavailable", "still loading", 0).retryAfterSeconds, null);
});

test("freshness: fresh, stale, failed, and unknown", () => {
  assert.deepEqual(describeFreshness(fresh), { tone: "fresh", summary: "Loaded 12 min ago", warning: null });

  const stale = describeFreshness({ ...fresh, stale: true, refreshing: true, age_seconds: 90_000 });
  assert.equal(stale.tone, "stale");
  assert.match(stale.warning, /refresh interval; a refresh is in progress/);

  const failed = describeFreshness({ ...fresh, stale: true, age_seconds: 7_200, last_error: "Databricks could not be reached." });
  assert.equal(failed.tone, "failed");
  assert.match(failed.warning, /latest refresh failed \(Databricks could not be reached\.\).*2 h old/);

  assert.equal(describeFreshness({ ...fresh, loaded_at: null, age_seconds: null }).tone, "unknown");
});

test("ages are rounded down to readable units", () => {
  assert.equal(formatAge(5), "under a minute");
  assert.equal(formatAge(3_599), "59 min");
  assert.equal(formatAge(3_600), "1 h");
  assert.equal(formatAge(86_400), "1 day");
  assert.equal(formatAge(3 * 86_400 + 5), "3 days");
});

test("the dataset's as_of date is kept separate from today's date", () => {
  const now = new Date("2026-10-27T15:30:00Z");
  assert.deepEqual(datasetDates("2026-03-31", now, "UTC"), {
    asOfLabel: "Mar 31, 2026",
    todayIso: "2026-10-27",
    todayLabel: "Oct 27, 2026",
    daysBehind: 210,
  });
  assert.equal(datasetDates("2026-10-27", now, "UTC").daysBehind, 0);
  assert.equal(datasetDates("2026-11-02", now, "UTC").daysBehind, 0); // never negative
});

test("today's date follows the given time zone (late evening UTC is already tomorrow in Asia)", () => {
  const instant = new Date("2026-10-27T22:30:00Z");
  assert.equal(isoDay(instant, "UTC"), "2026-10-27");
  assert.equal(isoDay(instant, "Asia/Kolkata"), "2026-10-28");
  assert.equal(isoDay(instant, "America/Los_Angeles"), "2026-10-27");
});

test("source labels", () => {
  assert.equal(sourceLabel("databricks"), "Databricks");
  assert.equal(sourceLabel("csv"), "Local CSV files");
  assert.equal(sourceLabel("synthetic"), "Static snapshot");
});
