"use client";

import * as React from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileStack, FileUp, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, templatesApi } from "@/lib/api";
import { formatDate, pageList, plural } from "@/lib/format";

/**
 * Templates are learned, not configured. The reviewer uploads a contract
 * that was already signed correctly and the app reads the positions off it.
 */
export function TemplatesScreen() {
  const queryClient = useQueryClient();
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [name, setName] = React.useState("");
  const [pending, setPending] = React.useState<File | null>(null);

  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["templates"],
    queryFn: () => templatesApi.list(),
  });

  const create = useMutation({
    mutationFn: ({ file, label }: { file: File; label: string }) =>
      templatesApi.create(file, label),
    onSuccess: (template) => {
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      setName("");
      setPending(null);
      if (template.ready) {
        toast.success(`Read ${template.signature_count} signature and ` +
          `${template.date_count} date positions`, {
          description: "Open it to check them before using it.",
        });
      } else {
        toast.warning("Nothing was found on that contract", {
          description:
            "It may not be signed yet. Open the template to place marks by hand.",
        });
      }
    },
    onError: (failure) =>
      toast.error("Could not read that contract", {
        description:
          failure instanceof ApiError ? failure.message : String(failure),
      }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => templatesApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      toast.success("Template deleted");
    },
    onError: (failure) =>
      toast.error("Could not delete the template", {
        description:
          failure instanceof ApiError ? failure.message : String(failure),
      }),
  });

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!pending) {
      toast.error("Choose a completed contract PDF first");
      return;
    }
    if (!name.trim()) {
      toast.error("Give the template a name");
      return;
    }
    create.mutate({ file: pending, label: name.trim() });
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Templates</h1>
        <p className="text-sm text-muted-foreground">
          Upload one contract that has already been signed correctly. The app
          reads where the signature and date sit, and stamps every later
          contract of that kind in the same places.
        </p>
      </div>

      <form
        onSubmit={submit}
        className="space-y-3 rounded-lg border border-border bg-card p-4"
      >
        <h2 className="text-sm font-semibold">Create a template</h2>

        <div className="flex flex-wrap items-end gap-3">
          <div className="grid gap-2">
            <Label htmlFor="template-name">Name</Label>
            <Input
              id="template-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Owner operator — Plan A"
              className="sm:w-72"
            />
          </div>

          <input
            ref={fileRef}
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            aria-label="Choose a completed signed contract"
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
            <FileUp aria-hidden />
            {pending ? "Change file" : "Choose signed PDF"}
          </Button>

          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? (
              <>
                <Loader2 className="animate-spin" aria-hidden />
                Reading…
              </>
            ) : (
              "Create template"
            )}
          </Button>
        </div>

        <p className="text-xs text-muted-foreground">
          {pending ? (
            <>
              Selected <span className="font-medium">{pending.name}</span>. Use
              a finished contract — one that already carries the signature and
              date.
            </>
          ) : (
            "Use a finished contract — one that already carries the signature and date."
          )}
        </p>
      </form>

      {isError ? (
        <div className="rounded-lg border border-danger-border bg-danger-muted px-4 py-6 text-center">
          <p className="font-medium text-danger">Could not load templates</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {error instanceof Error ? error.message : "Unknown error."}
          </p>
          <Button variant="outline" className="mt-3" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-20 w-full" />
          ))}
        </div>
      ) : data.length === 0 ? (
        <div className="rounded-lg border border-border bg-card px-4 py-12 text-center">
          <FileStack className="mx-auto size-6 text-muted-foreground" aria-hidden />
          <p className="mt-3 font-medium">No templates yet</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Take one contract you have already signed and finished, and upload
            it above. Everything after that gets signed the same way.
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {data.map((template) => (
            <li
              key={template.id}
              className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card px-4 py-3"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    href={`/templates/${template.id}`}
                    className="font-medium underline-offset-4 hover:underline"
                  >
                    {template.name}
                  </Link>
                  {template.ready ? (
                    <Badge variant="success">Ready</Badge>
                  ) : (
                    <Badge variant="warning">Nothing to stamp</Badge>
                  )}
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {template.signature_count}{" "}
                  {plural(template.signature_count, "signature")} ·{" "}
                  {template.date_count} {plural(template.date_count, "date")}
                  {template.pages_marked.length > 0 && (
                    <> · {pageList(template.pages_marked)}</>
                  )}{" "}
                  · from {template.source_filename} · added{" "}
                  {formatDate(template.created_at)}
                </p>
              </div>

              <Button variant="outline" size="sm" asChild>
                <Link href={`/templates/${template.id}`}>Open</Link>
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-danger"
                onClick={() => remove.mutate(template.id)}
                disabled={remove.isPending}
                aria-label={`Delete template ${template.name}`}
              >
                <Trash2 aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
