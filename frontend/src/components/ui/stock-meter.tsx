"use client";

import { motion } from "motion/react";

import { POSITION_STATUS } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import type { PositionStatus } from "@/lib/dashboard/types";

interface StockMeterProps {
  available: number;
  reorderPoint: number;
  safetyStock: number;
  status: PositionStatus;
  className?: string;
}

/** Available units relative to the reorder point; the tick marks the safety stock. Decorative. */
export function StockMeter({ available, reorderPoint, safetyStock, status, className }: StockMeterProps) {
  const scale = Math.max(reorderPoint, 1);
  const fill = Math.min(Math.max(available, 0) / scale, 1);
  const safety = Math.min(safetyStock / scale, 1);
  return (
    <div aria-hidden className={cn("relative h-1.5 overflow-hidden rounded-full bg-slate-100", className)}>
      <motion.div
        className={cn("h-full origin-left rounded-full", POSITION_STATUS[status].bar)}
        initial={{ scaleX: 0 }}
        animate={{ scaleX: fill }}
        transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1], delay: 0.1 }}
      />
      <span className="absolute inset-y-0 w-px bg-slate-400" style={{ left: `${safety * 100}%` }} />
    </div>
  );
}
