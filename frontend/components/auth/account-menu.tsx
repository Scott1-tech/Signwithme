"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { authApi } from "@/lib/api";

/** Who is signed in, and the way out. Hidden when the desk has no accounts. */
export function AccountMenu() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: ["auth-status"],
    queryFn: () => authApi.status(),
    staleTime: 30_000,
  });

  const signOut = useMutation({
    mutationFn: () => authApi.logout(),
    onSuccess: () => {
      queryClient.clear();
      router.replace("/login");
    },
    onError: (error) =>
      toast.error("Could not sign out", {
        description: error instanceof Error ? error.message : String(error),
      }),
  });

  if (!data?.login_required || !data.signed_in || !data.user) return null;

  return (
    <div className="flex items-center gap-2">
      <span className="hidden text-xs text-muted-foreground sm:inline">
        {data.user.label}
      </span>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => signOut.mutate()}
        disabled={signOut.isPending}
      >
        <LogOut aria-hidden />
        Sign out
      </Button>
    </div>
  );
}
