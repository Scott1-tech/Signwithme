"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, Copy } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { contractsApi } from "@/lib/api";

/**
 * This block gets pasted into a text message to the driver, so copying it
 * is one click and the result is confirmed.
 */
export function DriverNote({ contractId }: { contractId: string }) {
  const [copied, setCopied] = React.useState(false);

  const { data, isPending, isError, error } = useQuery({
    queryKey: ["driver-note", contractId],
    queryFn: () => contractsApi.driverNote(contractId),
  });

  const copy = async () => {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(data);
      setCopied(true);
      toast.success("Copied to the clipboard");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Could not copy", {
        description: "Select the text and copy it manually.",
      });
    }
  };

  return (
    <section aria-labelledby="driver-note-heading" className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 id="driver-note-heading" className="text-sm font-semibold">
            Note for the driver
          </h3>
          <p className="text-xs text-muted-foreground">
            Send this however you like. The app never contacts the driver.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={copy} disabled={!data}>
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>

      {isPending ? (
        <Skeleton className="h-20 w-full" />
      ) : isError ? (
        <p className="rounded-md border border-danger-border bg-danger-muted px-3 py-2 text-sm text-danger">
          Could not load the note: {error instanceof Error ? error.message : "unknown error"}
        </p>
      ) : (
        <pre className="overflow-x-auto rounded-md border border-border bg-muted px-3 py-2.5 font-mono text-[0.8125rem] leading-relaxed whitespace-pre-wrap">
          {data}
        </pre>
      )}
    </section>
  );
}
