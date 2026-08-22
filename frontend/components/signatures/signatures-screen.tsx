"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImageUp, Loader2, PenLine, Star, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, signaturesApi } from "@/lib/api";
import { formatDate } from "@/lib/format";

/**
 * The signature library. A carrier usually has more than one person who can
 * sign, so these are saved by name and chosen per contract.
 */
export function SignaturesScreen() {
  const queryClient = useQueryClient();
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [name, setName] = React.useState("");
  const [pending, setPending] = React.useState<File | null>(null);

  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["signatures"],
    queryFn: () => signaturesApi.list(),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["signatures"] });
  };

  const describe = (label: string) => (failure: unknown) =>
    toast.error(label, {
      description:
        failure instanceof ApiError ? failure.message : String(failure),
    });

  const create = useMutation({
    mutationFn: ({ file, label }: { file: File; label: string }) =>
      signaturesApi.create(file, label),
    onSuccess: (saved) => {
      invalidate();
      setName("");
      setPending(null);
      toast.success(`Saved “${saved.name}”`);
    },
    onError: describe("Could not save the signature"),
  });

  const makeDefault = useMutation({
    mutationFn: (id: string) => signaturesApi.makeDefault(id),
    onSuccess: () => {
      invalidate();
      toast.success("Default signature changed");
    },
    onError: describe("Could not change the default"),
  });

  const remove = useMutation({
    mutationFn: (id: string) => signaturesApi.remove(id),
    onSuccess: () => {
      invalidate();
      toast.success("Signature deleted");
    },
    onError: describe("Could not delete the signature"),
  });

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!pending) {
      toast.error("Choose a PNG first");
      return;
    }
    if (!name.trim()) {
      toast.error("Give the signature a name");
      return;
    }
    create.mutate({ file: pending, label: name.trim() });
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Signatures</h1>
        <p className="text-sm text-muted-foreground">
          Saved signature images. You choose one each time you upload a
          contract, so different people can sign different packets.
        </p>
      </div>

      <form
        onSubmit={submit}
        className="space-y-3 rounded-lg border border-border bg-card p-4"
      >
        <h2 className="text-sm font-semibold">Add a signature</h2>

        <div className="flex flex-wrap items-end gap-3">
          <div className="grid gap-2">
            <Label htmlFor="signature-name">Whose signature is this?</Label>
            <Input
              id="signature-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Dana Okafor"
              className="sm:w-64"
            />
          </div>

          <input
            ref={fileRef}
            type="file"
            accept="image/png,.png"
            className="sr-only"
            aria-label="Choose a signature PNG"
            onChange={(event) => {
              setPending(event.target.files?.[0] ?? null);
              event.target.value = "";
            }}
          />
          <Button
            type="button"
            variant="outline"
            onClick={() => fileRef.current?.click()}
          >
            <ImageUp aria-hidden />
            {pending ? "Change file" : "Choose PNG"}
          </Button>

          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <PenLine aria-hidden />
            )}
            Save signature
          </Button>
        </div>

        <p className="text-xs text-muted-foreground">
          {pending ? (
            <>
              Selected <span className="font-medium">{pending.name}</span>. PNG
              only — a transparent background stamps most cleanly.
            </>
          ) : (
            "PNG only. A transparent background stamps most cleanly."
          )}
        </p>
      </form>

      {isError ? (
        <div className="rounded-lg border border-danger-border bg-danger-muted px-4 py-6 text-center">
          <p className="font-medium text-danger">Could not load signatures</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {error instanceof Error ? error.message : "Unknown error."}
          </p>
          <Button variant="outline" className="mt-3" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : isPending ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-36 w-full" />
          ))}
        </div>
      ) : data.length === 0 ? (
        <div className="rounded-lg border border-border bg-card px-4 py-12 text-center">
          <PenLine className="mx-auto size-6 text-muted-foreground" aria-hidden />
          <p className="mt-3 font-medium">No signatures saved yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Add one above. A contract cannot be signed until at least one
            exists.
          </p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((asset) => (
            <div
              key={asset.id}
              className="flex flex-col gap-3 rounded-lg border border-border bg-card p-3"
            >
              <div className="flex h-24 items-center justify-center rounded-md bg-muted">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={signaturesApi.imageUrl(asset.id)}
                  alt={`Signature of ${asset.name}`}
                  className="max-h-full max-w-full object-contain"
                />
              </div>

              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-medium">{asset.name}</p>
                  <p className="text-xs text-muted-foreground">
                    Added {formatDate(asset.created_at)}
                  </p>
                </div>
                {asset.is_default && (
                  <Badge variant="success">
                    <Star className="size-3" aria-hidden />
                    Default
                  </Badge>
                )}
              </div>

              <div className="flex gap-2">
                {!asset.is_default && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => makeDefault.mutate(asset.id)}
                    disabled={makeDefault.isPending}
                  >
                    Make default
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  className="ml-auto text-danger"
                  onClick={() => remove.mutate(asset.id)}
                  disabled={remove.isPending}
                  aria-label={`Delete the signature of ${asset.name}`}
                >
                  <Trash2 aria-hidden />
                  Delete
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
