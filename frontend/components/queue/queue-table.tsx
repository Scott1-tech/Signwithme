"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { StatusBadge } from "@/components/status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ContractListItem } from "@/lib/types";

interface QueueTableProps {
  items: ContractListItem[];
  loading: boolean;
}

/**
 * Arrow keys move between rows, Enter opens. This person opens fifteen of
 * these a week and should not need the mouse.
 */
export function QueueTable({ items, loading }: QueueTableProps) {
  const router = useRouter();
  const rowRefs = React.useRef<(HTMLTableRowElement | null)[]>([]);
  const [focused, setFocused] = React.useState(0);

  React.useEffect(() => {
    setFocused(0);
  }, [items.length]);

  const move = (from: number, delta: number) => {
    const next = Math.min(Math.max(from + delta, 0), items.length - 1);
    setFocused(next);
    rowRefs.current[next]?.focus();
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTableRowElement>, index: number) => {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        move(index, 1);
        break;
      case "ArrowUp":
        event.preventDefault();
        move(index, -1);
        break;
      case "Home":
        event.preventDefault();
        move(index, -items.length);
        break;
      case "End":
        event.preventDefault();
        move(index, items.length);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        router.push(`/contracts/${items[index].id}`);
        break;
    }
  };

  if (loading) {
    return (
      <div className="rounded-lg border border-border">
        <div className="space-y-px p-2">
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-10 w-full" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Driver</TableHead>
            <TableHead>File</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Errors</TableHead>
            <TableHead className="text-right">Warnings</TableHead>
            <TableHead className="text-right">Pages</TableHead>
            <TableHead>Uploaded</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item, index) => (
            <TableRow
              key={item.id}
              ref={(node) => {
                rowRefs.current[index] = node;
              }}
              tabIndex={index === focused ? 0 : -1}
              onKeyDown={(event) => onKeyDown(event, index)}
              onFocus={() => setFocused(index)}
              onClick={() => router.push(`/contracts/${item.id}`)}
              className="cursor-pointer hover:bg-accent focus-visible:bg-accent"
              aria-label={`${item.driver_name ?? "Unknown driver"}, ${item.original_filename}`}
            >
              <TableCell className="font-medium">
                {item.driver_name ?? (
                  <span className="text-muted-foreground">Name not read</span>
                )}
              </TableCell>
              <TableCell className="max-w-[22rem] truncate text-muted-foreground">
                {item.original_filename}
              </TableCell>
              <TableCell>
                <StatusBadge status={item.status} />
              </TableCell>
              <TableCell
                className={cn(
                  "text-right tabular-nums",
                  item.error_count > 0 && "font-semibold text-danger",
                )}
              >
                {item.error_count}
              </TableCell>
              <TableCell
                className={cn(
                  "text-right tabular-nums",
                  item.warning_count > 0 && "text-warning",
                )}
              >
                {item.warning_count}
              </TableCell>
              <TableCell className="text-right tabular-nums text-muted-foreground">
                {item.page_count}
              </TableCell>
              <TableCell className="whitespace-nowrap text-muted-foreground">
                {formatDateTime(item.created_at)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
