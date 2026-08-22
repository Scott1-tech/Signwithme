"use client";

import * as React from "react";
import Link from "next/link";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Download, FileCheck2, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { contractsApi } from "@/lib/api";
import { formatDate, formatDateTime, plural } from "@/lib/format";

const PAGE_SIZE = 25;

/**
 * Finished contracts: signed, stamped, and stored. Read-only — an executed
 * contract is never edited, and a correction is uploaded as a new one.
 */
export function CompletedScreen() {
  const [search, setSearch] = React.useState("");
  const [debounced, setDebounced] = React.useState("");
  const [page, setPage] = React.useState(1);

  React.useEffect(() => {
    const timer = setTimeout(() => {
      setDebounced(search);
      setPage(1);
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);

  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["contracts", { status: "executed", q: debounced, page }],
    queryFn: () =>
      contractsApi.list({
        status: "executed",
        q: debounced || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            Completed contracts
          </h1>
          <p className="text-sm text-muted-foreground">
            Signed, stamped, and stored. These are kept for the driver
            qualification file and are never edited.
          </p>
        </div>

        <div className="relative w-full max-w-xs">
          <Search
            className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search driver or filename"
            aria-label="Search completed contracts"
            className="pl-8"
          />
        </div>
      </div>

      {isError ? (
        <div className="rounded-lg border border-danger-border bg-danger-muted px-4 py-6 text-center">
          <p className="font-medium text-danger">Could not load this list</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {error instanceof Error ? error.message : "Unknown error."}
          </p>
          <Button variant="outline" className="mt-3" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : isPending ? (
        <div className="space-y-px rounded-lg border border-border p-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-10 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-border bg-card px-4 py-12 text-center">
          <FileCheck2 className="mx-auto size-6 text-muted-foreground" aria-hidden />
          <p className="mt-3 font-medium">
            {debounced ? "Nothing matches that search" : "Nothing signed yet"}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {debounced
              ? "Try a different driver name or filename."
              : "Contracts appear here once they have been approved and stamped."}
          </p>
        </div>
      ) : (
        <>
          <div className="rounded-lg border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Driver</TableHead>
                  <TableHead>File</TableHead>
                  <TableHead>Template</TableHead>
                  <TableHead>Signed by</TableHead>
                  <TableHead>Dated</TableHead>
                  <TableHead>Completed</TableHead>
                  <TableHead className="text-right">Download</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="font-medium">
                      <Link
                        href={`/contracts/${item.id}`}
                        className="underline-offset-4 hover:underline"
                      >
                        {item.driver_name ?? "Name not read"}
                      </Link>
                    </TableCell>
                    <TableCell className="max-w-[16rem] truncate text-muted-foreground">
                      {item.original_filename}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {item.template_name ?? "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {item.signature_name ?? "—"}
                    </TableCell>
                    <TableCell className="tabular-nums text-muted-foreground">
                      {item.sign_date ? formatDate(item.sign_date) : "—"}
                    </TableCell>
                    <TableCell className="whitespace-nowrap tabular-nums text-muted-foreground">
                      {formatDateTime(item.updated_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="outline" size="sm" asChild>
                        <a href={contractsApi.downloadUrl(item.id)} download>
                          <Download aria-hidden />
                          PDF
                        </a>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              {total} completed {plural(total, "contract")}
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
