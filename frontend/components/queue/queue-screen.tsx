"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Inbox, Search } from "lucide-react";

import { QueueTable } from "@/components/queue/queue-table";
import { UploadDropzone } from "@/components/queue/upload-dropzone";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { contractsApi } from "@/lib/api";
import { plural } from "@/lib/format";

const FILTERS = [
  { value: "all", label: "All", status: undefined },
  { value: "needs_review", label: "Needs review", status: "needs_review" },
  { value: "clean", label: "Clean", status: "clean,approved" },
  { value: "executed", label: "Executed", status: "executed" },
] as const;

const PAGE_SIZE = 25;

export function QueueScreen() {
  const router = useRouter();
  const params = useSearchParams();

  const filter = params.get("filter") ?? "all";
  const search = params.get("q") ?? "";
  const page = Number(params.get("page") ?? "1") || 1;

  const [searchDraft, setSearchDraft] = React.useState(search);

  React.useEffect(() => setSearchDraft(search), [search]);

  const setParams = React.useCallback(
    (next: Record<string, string | undefined>) => {
      const updated = new URLSearchParams(params.toString());
      for (const [key, value] of Object.entries(next)) {
        if (value === undefined || value === "") updated.delete(key);
        else updated.set(key, value);
      }
      router.replace(`/?${updated.toString()}`, { scroll: false });
    },
    [params, router],
  );

  // Debounce the search box so typing does not fire a request per keystroke.
  React.useEffect(() => {
    if (searchDraft === search) return;
    const timer = setTimeout(
      () => setParams({ q: searchDraft || undefined, page: undefined }),
      250,
    );
    return () => clearTimeout(timer);
  }, [searchDraft, search, setParams]);

  const status = FILTERS.find((entry) => entry.value === filter)?.status;

  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["contracts", { status, search, page }],
    queryFn: () =>
      contractsApi.list({
        status,
        q: search || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const filtering = Boolean(search) || filter !== "all";

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Review queue</h1>
        <p className="text-sm text-muted-foreground">
          Upload a signed contract to see which pages the driver needs to fix.
        </p>
      </div>

      <UploadDropzone />

      <div className="flex flex-wrap items-center gap-3">
        <Tabs
          value={filter}
          onValueChange={(value) =>
            setParams({ filter: value === "all" ? undefined : value, page: undefined })
          }
        >
          <TabsList aria-label="Filter contracts by status">
            {FILTERS.map((entry) => (
              <TabsTrigger key={entry.value} value={entry.value}>
                {entry.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <div className="relative ml-auto w-full max-w-xs">
          <Search
            className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            value={searchDraft}
            onChange={(event) => setSearchDraft(event.target.value)}
            placeholder="Search driver or filename"
            aria-label="Search by driver name or filename"
            className="pl-8"
          />
        </div>
      </div>

      {isError ? (
        <div className="rounded-lg border border-danger-border bg-danger-muted px-4 py-6 text-center">
          <p className="font-medium text-danger">Could not load the queue</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {error instanceof Error ? error.message : "Unknown error."}
          </p>
          <Button variant="outline" className="mt-3" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : !isPending && items.length === 0 ? (
        <EmptyState filtering={filtering} onClear={() => setParams({ filter: undefined, q: undefined })} />
      ) : (
        <>
          <QueueTable items={items} loading={isPending} />

          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span aria-live="polite">
              {isPending
                ? "Loading…"
                : isFetching
                  ? "Updating…"
                  : `${total} ${plural(total, "contract")}`}
            </span>
            {lastPage > 1 && (
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setParams({ page: String(page - 1) })}
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
                  onClick={() => setParams({ page: String(page + 1) })}
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

function EmptyState({
  filtering,
  onClear,
}: {
  filtering: boolean;
  onClear: () => void;
}) {
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-12 text-center">
      <Inbox className="mx-auto size-6 text-muted-foreground" aria-hidden />
      {filtering ? (
        <>
          <p className="mt-3 font-medium">No contracts match this filter</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Try a different status, or clear the search.
          </p>
          <Button variant="outline" className="mt-3" onClick={onClear}>
            Clear filters
          </Button>
        </>
      ) : (
        <>
          <p className="mt-3 font-medium">Nothing in the queue yet</p>
          <div className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            <p>Here is how this works:</p>
            <ol className="mt-2 space-y-1 text-left">
              <li>1. Download the completed contract from DocuSign as a PDF.</li>
              <li>2. Drop it in the box above. Checking takes a few seconds.</li>
              <li>
                3. You get a page-numbered list of what is wrong, ready to send
                to the driver.
              </li>
              <li>
                4. When it is right, approve it and the carrier signature is
                stamped.
              </li>
            </ol>
            <p className="mt-3">
              First time?{" "}
              <a className="underline underline-offset-4" href="/settings">
                Set up the field map and signature
              </a>{" "}
              before the first real contract.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
