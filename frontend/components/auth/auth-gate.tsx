"use client";

import * as React from "react";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { authApi } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Keeps signed-out browsers off the desk.
 *
 * Accounts are opt-in: with none created the app behaves as it always has,
 * which is right for a tool that only answers to the machine it runs on.
 * Once an account exists — the same switch that lets the app be reached
 * over a network — every screen needs a session.
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();

  const { data, isPending, isError } = useQuery({
    queryKey: ["auth-status"],
    queryFn: () => authApi.status(),
    // Cheap, and it decides whether anything else may render.
    staleTime: 30_000,
    retry: 1,
  });

  const onLoginPage = pathname === "/login";
  const blocked = Boolean(data?.login_required && !data.signed_in);

  React.useEffect(() => {
    if (blocked && !onLoginPage) router.replace("/login");
  }, [blocked, onLoginPage, router]);

  // The login page renders on its own; it must not wait on this.
  if (onLoginPage) return <>{children}</>;

  if (isPending) {
    return (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-6 w-56" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  // If the check itself failed the backend is unreachable; let the screens
  // render and show their own error rather than trapping the reviewer here.
  if (isError) return <>{children}</>;

  if (blocked) {
    return (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-6 w-56" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  return <>{children}</>;
}
