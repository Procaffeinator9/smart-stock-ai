"use client";

import { animate, motion, useMotionValue, useReducedMotion, useTransform } from "motion/react";
import { useEffect } from "react";

interface CountUpProps {
  value: number;
  format: (value: number) => string;
  duration?: number;
  className?: string;
}

/**
 * Animates a number from its previous value to `value`. Screen readers get the final value
 * immediately; users who prefer reduced motion see it without animation.
 */
export function CountUp({ value, format, duration = 1.1, className }: CountUpProps) {
  const reduceMotion = useReducedMotion();
  const motionValue = useMotionValue(0);
  const text = useTransform(motionValue, (latest) => format(latest));

  useEffect(() => {
    if (reduceMotion) {
      motionValue.set(value);
      return;
    }
    const controls = animate(motionValue, value, { duration, ease: [0.16, 1, 0.3, 1] });
    return () => controls.stop();
  }, [value, duration, reduceMotion, motionValue]);

  return (
    <span className={className}>
      <motion.span aria-hidden className="tabular-nums">
        {text}
      </motion.span>
      <span className="sr-only">{format(value)}</span>
    </span>
  );
}
