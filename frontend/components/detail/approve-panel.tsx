"use client";

import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Download,
  Loader2,
  PenLine,
  ShieldAlert,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { ApiError, contractsApi } from "@/lib/api";
import { formatDateTime, pageList, plural } from "@/lib/format";
import type { ContractDetail } from "@/lib/types";

/**
 * The approve step is the legal basis for stamping the signature under
 * E-SIGN. The checkbox is never pre-checked, the name is never prefilled,
 * and neither can be skipped. Do not "streamline" this.
 */
export function ApprovePanel({ contract }: { contract: ContractDetail }) {
  const queryClient = useQueryClient();
  const [name, setName] = React.useState("");
  const [authorised, setAuthorised] = React.useState(false);

  const errors = contract.summary.error_count;
  const hasErrors = errors > 0;

  const onSettled = (updated: ContractDetail) => {
    queryClient.setQueryData(["contract", updated.id], updated);
    queryClient.invalidateQueries({ queryKey: ["contracts"] });
    queryClient.invalidateQueries({ queryKey: ["audit"] });
  };

  const reportError = (label: string) => (error: unknown) => {
    const message =
      error instanceof ApiError ? error.message : String(error ?? "Unknown error");
    toast.error(label, { description: message, duration: 10_000 });
  };

  const approve = useMutation({
    mutationFn: () =>
      contractsApi.approve(contract.id, {
        approved_by: name.trim(),
        acknowledge_errors: hasErrors,
      }),
    onSuccess: (updated) => {
      onSettled(updated);
      toast.success(
        updated.approval?.overridden
          ? "Approved and recorded as an override"
          : "Approved",
      );
    },
    onError: reportError("Could not approve"),
  });

  const execute = useMutation({
    mutationFn: () => contractsApi.execute(contract.id),
    onSuccess: (updated) => {
      onSettled(updated);
      toast.success("Signed and stored", {
        description: `Stamped on ${pageList(updated.approval?.pages_stamped ?? [])}.`,
      });
    },
    onError: reportError("Could not execute"),
  });

  /* --- Executed: show the record and the download --- */

  if (contract.status === "executed") {
    return (
      <section
        aria-labelledby="executed-heading"
        className="rounded-lg border border-border bg-card"
      >
        <div className="px-4 py-3">
          <h3 id="executed-heading" className="text-sm font-semibold">
            Executed
          </h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            This contract is final. A correction is uploaded as a new contract.
          </p>
        </div>
        <Separator />
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          {contract.approval && <ApprovalRecord contract={contract} />}
          <Button asChild>
            <a href={contractsApi.downloadUrl(contract.id)} download>
              <Download aria-hidden />
              Download signed PDF
            </a>
          </Button>
        </div>
      </section>
    );
  }

  /* --- Approved, waiting to be stamped --- */

  if (contract.approval) {
    return (
      <section
        aria-labelledby="approved-heading"
        className="rounded-lg border border-border bg-card"
      >
        <div className="px-4 py-3">
          <h3 id="approved-heading" className="text-sm font-semibold">
            Approved — ready to stamp
          </h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Applying the signature writes a new PDF. The original upload is kept.
          </p>
        </div>
        <Separator />
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <ApprovalRecord contract={contract} />
          <div className="flex flex-col items-end gap-1">
            <Button
              onClick={() => execute.mutate()}
              disabled={execute.isPending || !contract.signature_ready}
            >
              {execute.isPending ? (
                <>
                  <Loader2 className="animate-spin" aria-hidden />
                  Stamping…
                </>
              ) : (
                <>
                  <PenLine aria-hidden />
                  Apply signature
                </>
              )}
            </Button>
            {!contract.signature_ready && (
              <p className="text-xs text-danger">
                No signature image configured.{" "}
                <a className="underline underline-offset-4" href="/settings">
                  Upload one in settings
                </a>
                .
              </p>
            )}
          </div>
        </div>
      </section>
    );
  }

  /* --- Not approvable --- */

  if (!contract.can_approve) {
    return (
      <section className="rounded-lg border border-border bg-card px-4 py-3">
        <h3 className="text-sm font-semibold">Approval not available</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          A {contract.status} contract cannot be approved.
        </p>
      </section>
    );
  }

  /* --- The gate --- */

  const ready = name.trim().length > 0 && authorised;

  return (
    <section
      aria-labelledby="approve-heading"
      className="rounded-lg border border-border bg-card"
    >
      <div className="px-4 py-3">
        <h3 id="approve-heading" className="text-sm font-semibold">
          Approve and sign
        </h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Your name and the confirmation below are the legal record behind the
          signature.
        </p>
      </div>
      <Separator />

      <div className="space-y-4 px-4 py-4">
        {hasErrors && (
          <div className="flex items-start gap-2.5 rounded-md border border-danger-border bg-danger-muted px-3 py-2.5">
            <ShieldAlert className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
            <div className="text-sm">
              <p className="font-medium text-danger">
                {errors} unresolved {plural(errors, "error")}
              </p>
              <p className="mt-0.5 text-muted-foreground">
                You can still approve — you may have context the rules do not —
                but it will be recorded permanently as an override, naming you.
              </p>
            </div>
          </div>
        )}

        <div className="grid gap-2 sm:max-w-sm">
          <Label htmlFor="approved-by">Your full name</Label>
          <Input
            id="approved-by"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. Dana Okafor"
            autoComplete="off"
          />
        </div>

        <div className="flex items-start gap-2.5">
          <Checkbox
            id="authorise"
            checked={authorised}
            onCheckedChange={(value) => setAuthorised(value === true)}
            className="mt-0.5"
          />
          <Label htmlFor="authorise" className="leading-relaxed font-normal">
            I have reviewed this contract and authorise my signature to be
            applied.
          </Label>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => approve.mutate()} disabled={!ready || approve.isPending}>
            {approve.isPending ? (
              <>
                <Loader2 className="animate-spin" aria-hidden />
                Recording approval…
              </>
            ) : hasErrors ? (
              <>
                <AlertTriangle aria-hidden />
                Approve as an override
              </>
            ) : (
              "Approve"
            )}
          </Button>
          {!ready && (
            <p className="text-xs text-muted-foreground">
              Type your name and tick the box to continue.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

function ApprovalRecord({ contract }: { contract: ContractDetail }) {
  const approval = contract.approval;
  if (!approval) return null;

  return (
    <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-[auto_1fr]">
      <dt className="text-muted-foreground">Approved by</dt>
      <dd className="font-medium">{approval.approved_by}</dd>

      <dt className="text-muted-foreground">When</dt>
      <dd className="tabular-nums">{formatDateTime(approval.approved_at)}</dd>

      {approval.overridden && (
        <>
          <dt className="text-muted-foreground">Override</dt>
          <dd className="font-medium text-danger">
            Approved with {approval.error_count_at_approval}{" "}
            {plural(approval.error_count_at_approval, "error")} outstanding
          </dd>
        </>
      )}

      {approval.pages_stamped.length > 0 && (
        <>
          <dt className="text-muted-foreground">Signature</dt>
          <dd className="tabular-nums">{pageList(approval.pages_stamped)}</dd>
        </>
      )}
    </dl>
  );
}
