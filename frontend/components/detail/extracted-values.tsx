"use client";

import { ChevronDown } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { extractionSourceLabel } from "@/lib/format";
import type { ContractDetail } from "@/lib/types";

/**
 * Collapsed by default — this is for spot-checking, not for the main read.
 *
 * "Not found" and "blank" are shown differently on purpose. A field the
 * extractor never located usually means the field map is wrong; a field
 * found sitting empty means the driver skipped it.
 */
export function ExtractedValues({
  contract,
  onJumpToPage,
}: {
  contract: ContractDetail;
  onJumpToPage: (page: number) => void;
}) {
  return (
    <Collapsible>
      <CollapsibleTrigger className="group flex w-full items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-left text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
        <span className="font-semibold">Extracted values</span>
        <span className="text-xs text-muted-foreground">
          {contract.fields.length} fields · {extractionSourceLabel(contract.extraction_source)}
        </span>
        <ChevronDown
          className="ml-auto size-4 transition-transform group-data-[state=open]:rotate-180"
          aria-hidden
        />
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className="mt-2 rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Field</TableHead>
                <TableHead>Value</TableHead>
                <TableHead className="w-20 text-right">Page</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {contract.fields.map((field) => (
                <TableRow key={field.field_key}>
                  <TableCell>
                    <span className="font-medium">{field.label}</span>
                    <span className="ml-2 font-mono text-xs text-muted-foreground">
                      {field.field_key}
                    </span>
                  </TableCell>
                  <TableCell>
                    {!field.found ? (
                      <Badge variant="outline">Not found on the form</Badge>
                    ) : field.value ? (
                      <span className="font-mono text-[0.8125rem]">{field.value}</span>
                    ) : (
                      <Badge variant="outline">Found but blank</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {field.page !== null ? (
                      <button
                        type="button"
                        onClick={() => onJumpToPage(field.page!)}
                        className="rounded-sm underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                        aria-label={`Show page ${field.page} in the preview`}
                      >
                        {field.page}
                      </button>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
