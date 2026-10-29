import { cn } from "@/lib/cn";

/** Geometric mark: three rising stock levels inside a rounded square. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-8 shrink-0", className)}>
      <rect width="32" height="32" rx="9" fill="#4338ca" />
      <path d="M0 9a9 9 0 0 1 9-9h14a9 9 0 0 1 9 9v5C22 18 10 18 0 14z" fill="#6366f1" />
      <rect x="8" y="17" width="4" height="7" rx="1.5" fill="white" fillOpacity="0.55" />
      <rect x="14" y="12.5" width="4" height="11.5" rx="1.5" fill="white" fillOpacity="0.8" />
      <rect x="20" y="8" width="4" height="16" rx="1.5" fill="white" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("whitespace-nowrap text-[15px] font-semibold tracking-tight text-ink", className)}>
      SmartStock <span className="text-brand">AI</span>
    </span>
  );
}
