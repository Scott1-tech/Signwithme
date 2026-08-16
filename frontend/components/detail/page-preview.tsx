"use client";

import * as React from "react";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { contractsApi } from "@/lib/api";
import { pageList } from "@/lib/format";
import type { ContractDetail } from "@/lib/types";

interface PagePreviewProps {
  contract: ContractDetail;
  page: number;
  onPageChange: (page: number) => void;
}

/**
 * The backend renders pages to PNG. No pdf.js worker, no viewer to
 * maintain — just images.
 */
export function PagePreview({ contract, page, onPageChange }: PagePreviewProps) {
  const [boxes, setBoxes] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [failed, setFailed] = React.useState(false);
  const [jump, setJump] = React.useState(String(page));

  React.useEffect(() => setJump(String(page)), [page]);

  const clamp = (value: number) =>
    Math.min(Math.max(value, 1), Math.max(contract.page_count, 1));

  const source = contractsApi.previewUrl(contract.id, page, boxes);
  const stampedPages = contract.placements.map((placement) => placement.page);

  return (
    <section aria-labelledby="preview-heading" className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="preview-heading" className="text-sm font-semibold">
          Page preview
        </h3>

        <div className="flex items-center gap-2">
          <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
            <Checkbox
              checked={boxes}
              onCheckedChange={(value) => setBoxes(value === true)}
              aria-label="Show where the signature will be placed"
            />
            Show signature placement
          </label>
        </div>
      </div>

      {boxes && (
        <p className="text-xs text-muted-foreground">
          {stampedPages.length > 0
            ? `Signature will be stamped on ${pageList(stampedPages)}.`
            : "No placement resolved yet — check the signature settings."}
        </p>
      )}

      <div className="relative overflow-hidden rounded-lg border border-border bg-muted">
        {loading && !failed && (
          <div className="absolute inset-0 flex items-center justify-center">
            <Loader2 className="size-5 animate-spin text-muted-foreground" aria-hidden />
            <span className="sr-only">Loading page {page}</span>
          </div>
        )}

        {failed ? (
          <p className="px-4 py-16 text-center text-sm text-muted-foreground">
            Page {page} could not be rendered.
          </p>
        ) : (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            key={source}
            src={source}
            alt={`Page ${page} of ${contract.original_filename}`}
            className="mx-auto block h-auto w-full max-w-[820px]"
            onLoad={() => {
              setLoading(false);
              setFailed(false);
            }}
            onError={() => {
              setLoading(false);
              setFailed(true);
            }}
          />
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(clamp(page - 1))}
            disabled={page <= 1}
          >
            <ChevronLeft aria-hidden />
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(clamp(page + 1))}
            disabled={page >= contract.page_count}
          >
            Next
            <ChevronRight aria-hidden />
          </Button>
        </div>

        <form
          className="flex items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const value = Number(jump);
            if (Number.isFinite(value)) onPageChange(clamp(value));
          }}
        >
          <Label htmlFor="jump-to-page" className="text-xs text-muted-foreground">
            Go to page
          </Label>
          <Input
            id="jump-to-page"
            value={jump}
            onChange={(event) => setJump(event.target.value)}
            inputMode="numeric"
            className="h-8 w-16 text-center tabular-nums"
          />
          <span className="text-xs text-muted-foreground tabular-nums">
            of {contract.page_count}
          </span>
        </form>
      </div>
    </section>
  );
}
