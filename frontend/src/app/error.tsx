"use client";

import { RotateCw, TriangleAlert } from "lucide-react";
import { useEffect } from "react";

import { EmptyState } from "@/components/ui/empty-state";

export default function ErrorPage({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="rounded-2xl border border-line bg-surface shadow-card">
      <EmptyState
        icon={TriangleAlert}
        tone="danger"
        title="This page could not be displayed"
        description={error instanceof Error ? error.message : "An unexpected error occurred."}
        action={
          <button
            type="button"
            onClick={() => retry()}
            className="inline-flex items-center gap-2 rounded-lg bg-brand px-3.5 py-2 text-sm font-medium text-white shadow-sm hover:bg-brand-strong"
          >
            <RotateCw aria-hidden className="size-4" />
            Try again
          </button>
        }
        className="py-16"
      />
    </div>
  );
}
