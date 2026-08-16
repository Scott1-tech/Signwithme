"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FileText } from "lucide-react";

import { ApprovePanel } from "@/components/detail/approve-panel";
import { DriverNote } from "@/components/detail/driver-note";
import { ExtractedValues } from "@/components/detail/extracted-values";
import { FlagList } from "@/components/detail/flag-list";
import { PagePreview } from "@/components/detail/page-preview";
import { Verdict } from "@/components/detail/verdict";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { contractsApi } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export function DetailScreen({ contractId }: { contractId: string }) {
  const [page, setPage] = React.useState(1);
  const previewRef = React.useRef<HTMLDivElement>(null);

  const { data: contract, isPending, isError, error, refetch } = useQuery({
    queryKey: ["contract", contractId],
    queryFn: () => contractsApi.get(contractId),
  });

  // Land on the first page that needs fixing — that is what they came for.
  const firstBadPage = contract?.summary.pages_to_fix[0];
  const landed = React.useRef(false);
  React.useEffect(() => {
    if (!landed.current && firstBadPage) {
      setPage(firstBadPage);
      landed.current = true;
    }
  }, [firstBadPage]);

  const jumpToPage = React.useCallback((next: number) => {
    setPage(next);
    previewRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  if (isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-6 w-64" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-danger-border bg-danger-muted px-4 py-8 text-center">
        <p className="font-medium text-danger">Could not load this contract</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {error instanceof Error ? error.message : "Unknown error."}
        </p>
        <div className="mt-3 flex justify-center gap-2">
          <Button variant="outline" onClick={() => refetch()}>
            Try again
          </Button>
          <Button variant="ghost" asChild>
            <Link href="/">Back to the queue</Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground underline-offset-4 hover:underline"
        >
          <ArrowLeft className="size-3.5" aria-hidden />
          Back to the queue
        </Link>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="text-lg font-semibold tracking-tight">
            {contract.driver_name ?? "Driver name not read"}
          </h1>
          <StatusBadge status={contract.status} />
        </div>

        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <FileText className="size-3.5" aria-hidden />
            {contract.original_filename}
          </span>
          <span>{contract.page_count} pages</span>
          <span>Uploaded {formatDateTime(contract.created_at)}</span>
          {contract.ssn_masked && <span>SSN {contract.ssn_masked}</span>}
        </p>

        {contract.supersedes_id && (
          <p className="text-xs text-muted-foreground">
            Replaces{" "}
            <Link
              href={`/contracts/${contract.supersedes_id}`}
              className="underline underline-offset-4"
            >
              an earlier upload
            </Link>
            .
          </p>
        )}
        {contract.superseded_by_id && (
          <p className="text-xs text-warning">
            This upload was replaced by{" "}
            <Link
              href={`/contracts/${contract.superseded_by_id}`}
              className="underline underline-offset-4"
            >
              a corrected version
            </Link>
            .
          </p>
        )}
      </div>

      <Verdict contract={contract} />

      {contract.summary.error_count > 0 && <DriverNote contractId={contract.id} />}

      <FlagList contract={contract} onJumpToPage={jumpToPage} />

      <div ref={previewRef} className="scroll-mt-4">
        <PagePreview contract={contract} page={page} onPageChange={setPage} />
      </div>

      <ExtractedValues contract={contract} onJumpToPage={jumpToPage} />

      <ApprovePanel contract={contract} />
    </div>
  );
}
