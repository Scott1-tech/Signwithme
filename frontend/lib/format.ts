import type { ContractStatus } from "@/lib/types";

/** "pages 18 and 24", "pages 3, 18 and 24", "page 18". */
export function pageList(pages: number[]): string {
  if (pages.length === 0) return "";
  if (pages.length === 1) return `page ${pages[0]}`;
  const head = pages.slice(0, -1).join(", ");
  return `pages ${head} and ${pages[pages.length - 1]}`;
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return count === 1 ? one : many;
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDate(iso: string): string {
  const date = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

export const STATUS_LABELS: Record<ContractStatus, string> = {
  uploaded: "Uploaded",
  extracted: "Extracted",
  needs_review: "Needs review",
  clean: "Clean",
  approved: "Approved",
  executed: "Executed",
  superseded: "Superseded",
  void: "Void",
};

export function statusLabel(status: ContractStatus): string {
  return STATUS_LABELS[status] ?? status;
}

/** Human wording for how a value was located, shown on the detail screen. */
export function extractionSourceLabel(source: string): string {
  switch (source) {
    case "acroform":
      return "read from form fields";
    case "text":
      return "read from page text";
    case "acroform+text":
      return "read from form fields and page text";
    default:
      return "no values read";
  }
}
