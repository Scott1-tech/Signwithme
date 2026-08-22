"use client";

import * as React from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ChevronLeft, ChevronRight, Loader2, Save } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, templatesApi } from "@/lib/api";
import { pageList, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { TemplateMark } from "@/lib/types";

/**
 * What the app found on the signed contract, and where.
 *
 * Detection is reported rather than trusted: every mark can be switched off
 * before the template is used, because stamping in the wrong place writes
 * over something the driver filled in.
 */
export function TemplateDetail({ templateId }: { templateId: string }) {
  const queryClient = useQueryClient();
  const [page, setPage] = React.useState(1);
  const [draft, setDraft] = React.useState<TemplateMark[] | null>(null);

  const { data: template, isPending, isError, error, refetch } = useQuery({
    queryKey: ["template", templateId],
    queryFn: () => templatesApi.get(templateId),
  });

  React.useEffect(() => {
    if (template && draft === null) {
      setDraft(template.marks);
      setPage(template.pages_marked[0] ?? 1);
    }
  }, [template, draft]);

  const save = useMutation({
    mutationFn: (marks: TemplateMark[]) =>
      templatesApi.update(templateId, {
        marks: marks.map((mark) => ({
          kind: mark.kind,
          page: mark.page,
          x: mark.x,
          y: mark.y,
          width: mark.width,
          height: mark.height,
          sample_text: mark.sample_text,
          enabled: mark.enabled,
        })),
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["template", templateId], updated);
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      setDraft(updated.marks);
      toast.success("Template saved");
    },
    onError: (failure) =>
      toast.error("Could not save the template", {
        description:
          failure instanceof ApiError ? failure.message : String(failure),
      }),
  });

  if (isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-6 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-danger-border bg-danger-muted px-4 py-8 text-center">
        <p className="font-medium text-danger">Could not load this template</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {error instanceof Error ? error.message : "Unknown error."}
        </p>
        <div className="mt-3 flex justify-center gap-2">
          <Button variant="outline" onClick={() => refetch()}>
            Try again
          </Button>
          <Button variant="ghost" asChild>
            <Link href="/templates">Back to templates</Link>
          </Button>
        </div>
      </div>
    );
  }

  const marks = draft ?? template.marks;
  const enabled = marks.filter((mark) => mark.enabled);
  const dirty =
    JSON.stringify(marks.map((m) => m.enabled)) !==
    JSON.stringify(template.marks.map((m) => m.enabled));

  const toggle = (id: string, value: boolean) =>
    setDraft(
      marks.map((mark) => (mark.id === id ? { ...mark, enabled: value } : mark)),
    );

  const clamp = (value: number) =>
    Math.min(Math.max(value, 1), Math.max(template.page_count, 1));

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <Link
          href="/templates"
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground underline-offset-4 hover:underline"
        >
          <ArrowLeft className="size-3.5" aria-hidden />
          Back to templates
        </Link>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="text-lg font-semibold tracking-tight">
            {template.name}
          </h1>
          {enabled.length > 0 ? (
            <Badge variant="success">Ready to use</Badge>
          ) : (
            <Badge variant="warning">Nothing switched on</Badge>
          )}
        </div>

        <p className="text-xs text-muted-foreground">
          Read from {template.source_filename} · {template.page_count} pages ·{" "}
          {enabled.filter((m) => m.kind === "signature").length}{" "}
          {plural(enabled.filter((m) => m.kind === "signature").length, "signature")}{" "}
          and {enabled.filter((m) => m.kind === "date").length}{" "}
          {plural(enabled.filter((m) => m.kind === "date").length, "date")} switched on
        </p>
      </div>

      {marks.length === 0 ? (
        <div className="rounded-lg border border-warning-border bg-warning-muted px-4 py-6">
          <p className="font-medium text-warning">
            Nothing was found on this contract
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            The app looks for a signature image and a date printed beside it.
            If this contract has not been counter-signed yet, use one that has.
          </p>
        </div>
      ) : (
        <section aria-labelledby="marks-heading" className="space-y-2">
          <h2 id="marks-heading" className="text-sm font-semibold">
            What was found
          </h2>
          <ul className="space-y-2">
            {marks.map((mark) => (
              <li
                key={mark.id}
                className={cn(
                  "flex items-start gap-3 rounded-md border px-3 py-2.5",
                  mark.enabled ? "border-border bg-card" : "border-border bg-muted/50",
                )}
              >
                <Checkbox
                  checked={mark.enabled}
                  onCheckedChange={(value) => toggle(mark.id, value === true)}
                  className="mt-0.5"
                  aria-label={`Use this ${mark.kind} on page ${mark.page}`}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={mark.kind === "signature" ? "danger" : "default"}>
                      {mark.kind === "signature" ? "Signature" : "Date"}
                    </Badge>
                    <button
                      type="button"
                      onClick={() => setPage(mark.page)}
                      className="text-xs font-semibold tracking-wide text-muted-foreground uppercase underline-offset-4 hover:underline"
                    >
                      Page {mark.page}
                    </button>
                  </div>
                  {mark.sample_text && (
                    <p className="mt-1 leading-relaxed">
                      {mark.kind === "date" ? (
                        <>
                          Found the date{" "}
                          <span className="font-mono">{mark.sample_text}</span>{" "}
                          here — a new date will be written in its place.
                        </>
                      ) : (
                        <>Beside “{mark.sample_text}”</>
                      )}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>

          <div className="flex items-center gap-3">
            <Button
              size="sm"
              onClick={() => save.mutate(marks)}
              disabled={!dirty || save.isPending}
            >
              {save.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <Save aria-hidden />
              )}
              Save changes
            </Button>
            {dirty && (
              <p className="text-xs text-muted-foreground">
                Unsaved changes.
              </p>
            )}
          </div>
        </section>
      )}

      <section aria-labelledby="preview-heading" className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="preview-heading" className="text-sm font-semibold">
            Where they sit
          </h2>
          <p className="text-xs text-muted-foreground">
            Red is a signature, blue is a date.
            {template.pages_marked.length > 0 && (
              <> Marks are on {pageList(template.pages_marked)}.</>
            )}
          </p>
        </div>

        <div className="overflow-hidden rounded-lg border border-border bg-muted">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={templatesApi.previewUrl(template.id, page)}
            alt={`Page ${page} of the template with its marks drawn`}
            className="mx-auto block h-auto w-full max-w-[820px]"
          />
        </div>

        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage(clamp(page - 1))}
            disabled={page <= 1}
          >
            <ChevronLeft aria-hidden />
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage(clamp(page + 1))}
            disabled={page >= template.page_count}
          >
            Next
            <ChevronRight aria-hidden />
          </Button>
          <span className="ml-2 text-xs text-muted-foreground tabular-nums">
            Page {page} of {template.page_count}
          </span>
        </div>
      </section>
    </div>
  );
}
