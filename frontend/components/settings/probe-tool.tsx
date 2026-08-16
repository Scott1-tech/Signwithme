"use client";

import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { configApi } from "@/lib/api";
import type { ProbeResult } from "@/lib/types";

/**
 * Answers the day-one questions: are the returned PDFs flattened or do they
 * still have form fields, and exactly how is each label written?
 */
export function ProbeTool() {
  const [result, setResult] = React.useState<ProbeResult | null>(null);
  const [filter, setFilter] = React.useState("");
  const inputRef = React.useRef<HTMLInputElement>(null);

  const probe = useMutation({
    mutationFn: (file: File) => configApi.probe(file),
    onSuccess: (data) => {
      setResult(data);
      toast.success(
        data.has_acroform
          ? `Found ${data.widgets.length} form fields across ${data.page_count} pages`
          : `No form fields — this PDF is flattened, so extraction uses the page text`,
      );
    },
    onError: (error) =>
      toast.error("Could not read that PDF", {
        description: error instanceof Error ? error.message : String(error),
      }),
  });

  const needle = filter.trim().toLowerCase();
  const widgets = needle
    ? result?.widgets.filter((widget) => widget.name.toLowerCase().includes(needle))
    : result?.widgets;
  const pages = needle
    ? result?.pages.filter((page) => page.text.toLowerCase().includes(needle))
    : result?.pages;

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold">Probe a sample contract</h3>
        <p className="text-xs text-muted-foreground">
          Upload a real signed PDF to see what it actually contains, then fix
          the anchors above to match. Nothing is stored and no field values are
          returned.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          aria-label="Upload a sample PDF to probe"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) probe.mutate(file);
            event.target.value = "";
          }}
        />
        <Button
          variant="outline"
          onClick={() => inputRef.current?.click()}
          disabled={probe.isPending}
        >
          {probe.isPending ? (
            <>
              <Loader2 className="animate-spin" aria-hidden />
              Reading…
            </>
          ) : (
            <>
              <Search aria-hidden />
              Choose a sample PDF
            </>
          )}
        </Button>

        {result && (
          <Badge variant={result.has_acroform ? "success" : "outline"}>
            {result.has_acroform
              ? `${result.widgets.length} form fields`
              : "Flattened — no form fields"}
          </Badge>
        )}
      </div>

      {result && (
        <div className="space-y-3">
          <div className="grid gap-2 sm:max-w-sm">
            <Label htmlFor="probe-filter">Filter</Label>
            <Input
              id="probe-filter"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="e.g. expiration"
            />
          </div>

          <Tabs defaultValue={result.has_acroform ? "widgets" : "text"}>
            <TabsList>
              <TabsTrigger value="widgets">
                Form fields ({widgets?.length ?? 0})
              </TabsTrigger>
              <TabsTrigger value="text">
                Page text ({pages?.length ?? 0})
              </TabsTrigger>
            </TabsList>

            <TabsContent value="widgets">
              {widgets && widgets.length > 0 ? (
                <ul className="max-h-80 overflow-y-auto rounded-lg border border-border divide-y divide-border">
                  {widgets.map((widget, index) => (
                    <li
                      key={`${widget.page}-${widget.name}-${index}`}
                      className="flex items-center gap-3 px-3 py-1.5 text-xs"
                    >
                      <span className="w-12 shrink-0 text-muted-foreground tabular-nums">
                        p{widget.page}
                      </span>
                      <span className="flex-1 font-mono">{widget.name}</span>
                      <span className="text-muted-foreground">{widget.type}</span>
                      {widget.has_value && <Badge variant="outline">has a value</Badge>}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="rounded-lg border border-border px-3 py-6 text-center text-sm text-muted-foreground">
                  No form fields match.
                </p>
              )}
            </TabsContent>

            <TabsContent value="text">
              {pages && pages.length > 0 ? (
                <div className="max-h-80 space-y-3 overflow-y-auto rounded-lg border border-border p-3">
                  {pages.map((page) => (
                    <div key={page.page}>
                      <p className="text-xs font-semibold text-muted-foreground">
                        Page {page.page}
                      </p>
                      <pre className="mt-1 font-mono text-[0.75rem] leading-relaxed whitespace-pre-wrap">
                        {page.text || "(no text on this page)"}
                      </pre>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="rounded-lg border border-border px-3 py-6 text-center text-sm text-muted-foreground">
                  No page text matches.
                </p>
              )}
            </TabsContent>
          </Tabs>
        </div>
      )}
    </div>
  );
}
