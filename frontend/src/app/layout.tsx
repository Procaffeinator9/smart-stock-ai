import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";

import { AppShell } from "@/components/shell/app-shell";
import { BackendStatus, StatusPill } from "@/components/shell/backend-status";
import { getProductIndex, getSnapshotMeta } from "@/lib/dashboard/snapshot";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: { default: "SmartStock AI", template: "%s · SmartStock AI" },
  description: "Retail inventory intelligence: demand forecasting and replenishment.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full">
        <AppShell
          meta={getSnapshotMeta()}
          products={getProductIndex()}
          status={
            // Request-time API check in its own boundary so the rest of the shell prerenders.
            <Suspense fallback={<StatusPill state="checking" label="Checking API…" />}>
              <BackendStatus />
            </Suspense>
          }
        >
          {children}
        </AppShell>
      </body>
    </html>
  );
}
