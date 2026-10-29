import {
  Boxes,
  ClipboardList,
  LayoutDashboard,
  PackagePlus,
  Sparkles,
  TrendingUp,
  Truck,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  icon: LucideIcon;
  description: string;
  /** Sections without an href are planned for a later phase and render as "Soon". */
  href?: string;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Overview", href: "/", icon: LayoutDashboard, description: "KPIs, sales, alerts and forecast preview" },
  { label: "Inventory", href: "/inventory", icon: Boxes, description: "Stock positions by store and product" },
  { label: "Replenishment", href: "/replenishment", icon: PackagePlus, description: "Reorder worklist and suggested quantities" },
  { label: "Sales", href: "/sales", icon: TrendingUp, description: "Revenue, margin, promotions and product performance" },
  { label: "Purchase Orders", href: "/purchase-orders", icon: ClipboardList, description: "Order pipeline and delivery performance" },
  { label: "Suppliers", href: "/suppliers", icon: Truck, description: "Reliability, lead times and stock risk by supplier" },
  { label: "AI Copilot", icon: Sparkles, description: "Ask questions about your inventory" },
];

/** The section a path belongs to: an exact match, or a page nested under it (e.g. /suppliers/SUP-0001). */
export function navItemFor(pathname: string): NavItem | undefined {
  return NAV_ITEMS.find((item) => item.href && (item.href === pathname || (item.href !== "/" && pathname.startsWith(`${item.href}/`))));
}

export function pageTitle(pathname: string): string {
  return navItemFor(pathname)?.label ?? "Page not found";
}
