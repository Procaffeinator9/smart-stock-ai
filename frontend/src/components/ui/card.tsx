"use client";

import { motion, type Variants } from "motion/react";
import { useId, type ReactNode } from "react";

import { cn } from "@/lib/cn";

export const cardClassName =
  "rounded-2xl border border-line bg-surface shadow-card transition-shadow duration-300 hover:shadow-card-hover";

/** Entrance used by every dashboard block; the parent staggers them. */
export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] } },
};

interface CardProps {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

export function Card({ title, description, action, footer, children, className, bodyClassName }: CardProps) {
  const headingId = useId();
  return (
    <motion.section
      variants={fadeUp}
      aria-labelledby={headingId}
      className={cn(cardClassName, "flex min-w-0 flex-col", className)}
    >
      <header className="flex flex-wrap items-start justify-between gap-3 px-5 pt-5">
        <div className="min-w-0">
          <h2 id={headingId} className="text-[15px] font-semibold tracking-tight text-ink">
            {title}
          </h2>
          {description && <p className="mt-0.5 text-[13px] leading-5 text-ink-muted">{description}</p>}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </header>
      <div className={cn("flex-1 px-5 pb-5 pt-4", bodyClassName)}>{children}</div>
      {footer && (
        <footer className="border-t border-line px-5 py-3 text-xs leading-5 text-ink-subtle">{footer}</footer>
      )}
    </motion.section>
  );
}
