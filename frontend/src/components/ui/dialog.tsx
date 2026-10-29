"use client";

import { AnimatePresence, motion, type TargetAndTransition } from "motion/react";
import { useEffect, useRef, type ReactNode, type SyntheticEvent } from "react";

import { cn } from "@/lib/cn";

type Placement = "center" | "top" | "left";

const PANEL_MOTION: Record<
  Placement,
  { initial: TargetAndTransition; animate: TargetAndTransition; exit: TargetAndTransition }
> = {
  center: {
    initial: { opacity: 0, scale: 0.97, y: 8 },
    animate: { opacity: 1, scale: 1, y: 0 },
    exit: { opacity: 0, scale: 0.98, y: 4 },
  },
  top: {
    initial: { opacity: 0, scale: 0.98, y: -8 },
    animate: { opacity: 1, scale: 1, y: 0 },
    exit: { opacity: 0, scale: 0.98, y: -6 },
  },
  left: {
    initial: { x: "-100%" },
    animate: { x: 0 },
    exit: { x: "-100%" },
  },
};

const DIALOG_POSITION: Record<Placement, string> = {
  center: "m-auto w-[min(92vw,34rem)]",
  top: "mx-auto mt-[10vh] w-[min(94vw,40rem)]",
  left: "my-0 ml-0 mr-auto h-dvh max-h-dvh w-[min(86vw,20rem)]",
};

interface DialogProps {
  open: boolean;
  onClose: () => void;
  labelledBy: string;
  placement?: Placement;
  className?: string;
  children: ReactNode;
}

/**
 * Modal built on the native <dialog> element: the browser provides the focus trap, Esc handling,
 * inert background, and focus restoration. Motion animates the panel in and out.
 */
export function Dialog({ open, onClose, labelledBy, placement = "center", className, children }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (open && dialog && !dialog.open) dialog.showModal();
  }, [open]);

  function onCancel(event: SyntheticEvent<HTMLDialogElement>) {
    // Esc: let the exit animation run, then close in onExitComplete.
    event.preventDefault();
    onClose();
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby={labelledBy}
      onCancel={onCancel}
      onClick={(event) => {
        if (event.target === ref.current) onClose(); // click on the backdrop
      }}
      className={cn("app-dialog max-w-none overflow-visible bg-transparent p-0", DIALOG_POSITION[placement])}
    >
      <AnimatePresence onExitComplete={() => ref.current?.close()}>
        {open && (
          <motion.div
            {...PANEL_MOTION[placement]}
            transition={placement === "left" ? { type: "spring", stiffness: 380, damping: 38 } : { duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className={cn("bg-surface shadow-pop", placement === "left" ? "h-full" : "rounded-2xl border border-line", className)}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </dialog>
  );
}
