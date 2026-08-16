"use client";

import * as React from "react";
import Link from "next/link";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Download, ScrollText } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { auditApi } from "@/lib/api";
import { formatDateTime, pageList, plural } from "@/lib/format";

const PAGE_SIZE = 50;

export function AuditScreen() {
  const [page, setPage] = React.useState(1);

  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["audit", page],
    queryFn: () => auditApi.list(page, PAGE_SIZE),
    placeholderData: keepPreviousData,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Audit log</h1>
          <p className="text-sm text-muted-foreground">
            Every approval, in the order it happened. Nothing here can be
            edited or deleted.
          </p>
        </div>
        <Button variant="outline" asChild>
          <a href={auditApi.exportUrl()} download>
            <Download aria-hidden />
            Export CSV
          </a>
        </Button>
      </div>

      {isError ? (
        <div className="rounded-lg border border-danger-border bg-danger-muted px-4 py-6 text-center">
          <p className="font-medium text-danger">Could not load the audit log</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {error instanceof Error ? error.message : "Unknown error."}
          </p>
          <Button variant="outline" className="mt-3" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : isPending ? (
        <div className="space-y-px rounded-lg border border-border p-2">
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-10 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-border bg-card px-4 py-12 text-center">
          <ScrollText className="mx-auto size-6 text-muted-foreground" aria-hidden />
          <p className="mt-3 font-medium">No approvals yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            An entry appears here the moment a contract is approved.
          </p>
        </div>
      ) : (
        <>
          <div className="rounded-lg border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Approved</TableHead>
                  <TableHead>By</TableHead>
                  <TableHead>Driver</TableHead>
                  <TableHead>File</TableHead>
                  <TableHead>Outcome</TableHead>
                  <TableHead>Pages stamped</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="whitespace-nowrap tabular-nums">
                      {formatDateTime(entry.approved_at)}
                    </TableCell>
                    <TableCell className="font-medium">{entry.approved_by}</TableCell>
                    <TableCell>
                      {entry.driver_name ?? (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="max-w-[18rem] truncate">
                      <Link
                        href={`/contracts/${entry.contract_id}`}
                        className="text-muted-foreground underline-offset-4 hover:underline"
                      >
                        {entry.original_filename ?? entry.contract_id}
                      </Link>
                    </TableCell>
                    <TableCell>
                      {entry.overridden ? (
                        <Badge variant="danger">
                          Override · {entry.error_count_at_approval}{" "}
                          {plural(entry.error_count_at_approval, "error")}
                        </Badge>
                      ) : (
                        <Badge variant="success">Clean</Badge>
                      )}
                    </TableCell>
                    <TableCell className="tabular-nums text-muted-foreground">
                      {entry.pages_stamped.length > 0
                        ? pageList(entry.pages_stamped)
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              {total} {plural(total, "approval")}
            </span>
            {lastPage > 1 && (
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((value) => value - 1)}
                >
                  Previous
                </Button>
                <span className="tabular-nums">
                  Page {page} of {lastPage}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= lastPage}
                  onClick={() => setPage((value) => value + 1)}
                >
                  Next
                </Button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
