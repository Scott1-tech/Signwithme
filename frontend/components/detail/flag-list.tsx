"use client";

import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ChevronDown, Info, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { contractsApi } from "@/lib/api";
import { plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ContractDetail, Flag } from "@/lib/types";

interface FlagListProps {
  contract: ContractDetail;
  onJumpToPage: (page: number) => void;
}

export function FlagList({ contract, onJumpToPage }: FlagListProps) {
  const errors = contract.flags.filter(
    (flag) => flag.severity === "error" && !flag.resolved,
  );
  const warnings = contract.flags.filter(
    (flag) => flag.severity === "warning" && !flag.resolved,
  );
  const dismissed = contract.flags.filter((flag) => flag.resolved);

  const labelFor = React.useCallback(
    (fieldKey: string) =>
      contract.fields.find((field) => field.field_key === fieldKey)?.label ??
      fieldKey,
    [contract.fields],
  );

  if (errors.length === 0 && warnings.length === 0 && dismissed.length === 0) {
    return null;
  }

  return (
    <section aria-labelledby="flags-heading" className="space-y-3">
      <h3 id="flags-heading" className="text-sm font-semibold">
        What the checks found
      </h3>

      {errors.length > 0 && (
        <ul className="space-y-2">
          {errors.map((flag) => (
            <FlagRow
              key={flag.id}
              flag={flag}
              label={labelFor(flag.field_key)}
              onJumpToPage={onJumpToPage}
            />
          ))}
        </ul>
      )}

      {warnings.length > 0 && (
        <Collapsible>
          <CollapsibleTrigger className="group flex w-full items-center gap-2 rounded-md border border-warning-border bg-warning-muted px-3 py-2 text-left text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
            <Info className="size-4 text-warning" aria-hidden />
            <span className="font-medium text-warning">
              {warnings.length} {plural(warnings.length, "warning")}
            </span>
            <span className="text-muted-foreground">— nothing blocking</span>
            <ChevronDown
              className="ml-auto size-4 transition-transform group-data-[state=open]:rotate-180"
              aria-hidden
            />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <ul className="mt-2 space-y-2">
              {warnings.map((flag) => (
                <FlagRow
                  key={flag.id}
                  flag={flag}
                  label={labelFor(flag.field_key)}
                  onJumpToPage={onJumpToPage}
                  dismissible={contract.status !== "executed"}
                  contractId={contract.id}
                />
              ))}
            </ul>
          </CollapsibleContent>
        </Collapsible>
      )}

      {dismissed.length > 0 && (
        <Collapsible>
          <CollapsibleTrigger className="group flex items-center gap-1.5 text-xs text-muted-foreground underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
            <ChevronDown
              className="size-3.5 transition-transform group-data-[state=open]:rotate-180"
              aria-hidden
            />
            {dismissed.length} dismissed
          </CollapsibleTrigger>
          <CollapsibleContent>
            <ul className="mt-2 space-y-1">
              {dismissed.map((flag) => (
                <li
                  key={flag.id}
                  className="px-3 text-xs text-muted-foreground line-through"
                >
                  {flag.page !== null && `page ${flag.page}: `}
                  {flag.message}
                </li>
              ))}
            </ul>
          </CollapsibleContent>
        </Collapsible>
      )}
    </section>
  );
}

function FlagRow({
  flag,
  label,
  onJumpToPage,
  dismissible = false,
  contractId,
}: {
  flag: Flag;
  label: string;
  onJumpToPage: (page: number) => void;
  dismissible?: boolean;
  contractId?: string;
}) {
  const queryClient = useQueryClient();
  const isError = flag.severity === "error";

  const dismiss = useMutation({
    mutationFn: () => contractsApi.resolveFlag(contractId!, flag.id, true),
    onSuccess: (updated) => {
      queryClient.setQueryData(["contract", updated.id], updated);
      queryClient.invalidateQueries({ queryKey: ["contracts"] });
      toast.success("Warning dismissed");
    },
    onError: (error) =>
      toast.error("Could not dismiss the warning", {
        description: error instanceof Error ? error.message : String(error),
      }),
  });

  const jumpable = flag.page !== null;

  return (
    <li
      className={cn(
        "flex items-start gap-3 rounded-md border px-3 py-2.5",
        isError
          ? "border-danger-border bg-danger-muted"
          : "border-border bg-card",
      )}
    >
      {isError && (
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
      )}

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          {jumpable ? (
            <button
              type="button"
              onClick={() => onJumpToPage(flag.page!)}
              className="rounded-sm text-xs font-semibold tracking-wide text-muted-foreground uppercase underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              aria-label={`Show page ${flag.page} in the preview`}
            >
              Page {flag.page}
            </button>
          ) : (
            <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              No page
            </span>
          )}
          <span className="text-xs text-muted-foreground">{label}</span>
        </div>
        {/* Generous line height: these get read carefully. */}
        <p className="mt-1 leading-relaxed">{flag.message}</p>
      </div>

      {dismissible && contractId && (
        <Button
          variant="ghost"
          size="icon"
          className="size-7 shrink-0"
          onClick={() => dismiss.mutate()}
          disabled={dismiss.isPending}
          aria-label={`Dismiss warning: ${flag.message}`}
          title="Dismiss this warning"
        >
          <X className="size-3.5" />
        </Button>
      )}
    </li>
  );
}
