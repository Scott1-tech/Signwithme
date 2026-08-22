"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Lock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, authApi } from "@/lib/api";

export function LoginScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [problem, setProblem] = React.useState<string | null>(null);

  const { data: status } = useQuery({
    queryKey: ["auth-status"],
    queryFn: () => authApi.status(),
  });

  // Already in, or this desk has no accounts at all: nothing to do here.
  React.useEffect(() => {
    if (status && (!status.login_required || status.signed_in)) {
      router.replace("/");
    }
  }, [status, router]);

  const signIn = useMutation({
    mutationFn: () => authApi.login({ username, password }),
    onSuccess: () => {
      queryClient.invalidateQueries();
      router.replace("/");
    },
    onError: (error) => {
      setProblem(
        error instanceof ApiError
          ? error.message
          : "Could not reach the desk. Is it running?",
      );
      setPassword("");
    },
  });

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setProblem(null);
    if (!username.trim() || !password) {
      setProblem("Enter your username and password.");
      return;
    }
    signIn.mutate();
  };

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-sm flex-col justify-center">
      <div className="mb-6">
        <div className="mb-3 flex size-9 items-center justify-center rounded-md border border-border bg-card">
          <Lock className="size-4 text-muted-foreground" aria-hidden />
        </div>
        <h1 className="text-lg font-semibold tracking-tight">
          Contract Review Desk
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Sign in to review and sign driver contracts.
        </p>
      </div>

      <form onSubmit={submit} className="space-y-4" noValidate>
        <div className="grid gap-2">
          <Label htmlFor="username">Username</Label>
          <Input
            id="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            autoCapitalize="none"
            autoFocus
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />
        </div>

        {problem && (
          <p
            role="alert"
            className="rounded-md border border-danger-border bg-danger-muted px-3 py-2 text-sm text-danger"
          >
            {problem}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={signIn.isPending}>
          {signIn.isPending && <Loader2 className="animate-spin" aria-hidden />}
          Sign in
        </Button>
      </form>

      <p className="mt-6 text-xs text-muted-foreground">
        Accounts are created on the machine running the desk, with
        <code className="mx-1 rounded bg-muted px-1 py-0.5 font-mono text-[0.7rem]">
          python -m app.cli create-user
        </code>
        . There is no sign-up page: these files hold driver Social Security
        numbers.
      </p>
    </div>
  );
}
