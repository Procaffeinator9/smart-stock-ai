// Static, offline snapshot (backend/scripts/export_dashboard_snapshot.py). Since Phase 5A the
// Overview page reads live data from GET /api/v1/overview; this file still feeds the search
// palette's product index and the About dialog's metadata.
import rawSnapshot from "@/data/overview-snapshot.json";

import type { OverviewSnapshot, ProductIndexEntry, SnapshotMeta } from "./types";

const SUPPORTED_SCHEMA_VERSION = 1;

function loadSnapshot(): OverviewSnapshot {
  const snapshot = rawSnapshot as unknown as OverviewSnapshot;
  if (snapshot?.meta?.schema_version !== SUPPORTED_SCHEMA_VERSION) {
    throw new Error(
      "Dashboard snapshot has an unsupported format. Re-run backend/scripts/export_dashboard_snapshot.py.",
    );
  }
  return snapshot;
}

export function getProductIndex(): ProductIndexEntry[] {
  return loadSnapshot().products;
}

export function getSnapshotMeta(): SnapshotMeta {
  return loadSnapshot().meta;
}
