"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { AccountMenu } from "@/components/auth/account-menu";
import { ThemeToggle } from "@/components/theme-toggle";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Upload" },
  { href: "/templates", label: "Templates" },
  { href: "/signatures", label: "Signatures" },
  { href: "/completed", label: "Completed" },
  { href: "/audit", label: "Audit log" },
  { href: "/settings", label: "Settings" },
];

export function SiteNav() {
  const pathname = usePathname();
  // Nothing to navigate to until you are signed in.
  const signedOut = pathname === "/login";

  return (
    <header className="border-b border-border bg-background">
      <div className="mx-auto flex h-12 max-w-[1400px] items-center gap-6 px-4">
        <Link href="/" className="text-sm font-semibold tracking-tight">
          Contract Review Desk
        </Link>

        <nav aria-label="Main" className="flex items-center gap-1">
          {(signedOut ? [] : LINKS).map((link) => {
            const active =
              link.href === "/"
                ? pathname === "/" || pathname.startsWith("/contracts")
                : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-md px-2.5 py-1 text-sm transition-colors",
                  active
                    ? "bg-secondary font-medium text-secondary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <span className="hidden text-xs text-muted-foreground lg:inline">
            Local only · no driver data leaves this machine
          </span>
          {!signedOut && <AccountMenu />}
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
