import { ArrowRight, Compass } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/ui/empty-state";

export default function NotFound() {
  return (
    <div className="rounded-2xl border border-line bg-surface shadow-card">
      <EmptyState
        icon={Compass}
        title="Page not found"
        description="This page doesn't exist. Sections marked “Soon” in the sidebar are planned for a later phase."
        action={
          <Link
            href="/"
            className="inline-flex items-center gap-2 rounded-lg bg-brand px-3.5 py-2 text-sm font-medium text-white shadow-sm hover:bg-brand-strong"
          >
            Go to Overview
            <ArrowRight aria-hidden className="size-4" />
          </Link>
        }
        className="py-16"
      />
    </div>
  );
}
