import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Toaster } from "sonner";

import { SiteNav } from "@/components/site-nav";
import { Providers } from "@/app/providers";
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
  title: "Driver Contract Review Desk",
  description:
    "Review signed driver contracts against FMCSA rules and stamp the carrier signature.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        <Providers>
          <div className="min-h-screen">
            <SiteNav />
            <main className="mx-auto max-w-[1400px] px-4 py-6">{children}</main>
          </div>
          <Toaster position="bottom-right" closeButton richColors />
        </Providers>
      </body>
    </html>
  );
}
