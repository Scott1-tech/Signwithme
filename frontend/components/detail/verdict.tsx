"use client";

import { AlertTriangle, CheckCircle2, FileCheck2 } from "lucide-react";

import { pageList, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ContractDetail } from "@/lib/types";

/**
 * The answer to the one question this screen exists to answer: which pages
 * does the driver need to fix? Nothing sits above this.
 */
export function Verdict({ contract }: { contract: ContractDetail }) {
  const { error_count: errors, warning_count: warnings, pages_to_fix: pages } =
    contract.summary;
  const executed = contract.status === "executed";

  let tone: "danger" | "success" | "neutral";
  let Icon: typeof AlertTriangle;
  let headline: string;
  let detail: string;

  if (executed) {
    // Terminal state wins. A signed contract is final, so it must never
    // still be telling the reviewer to send a note and upload a correction.
    tone = "neutral";
    Icon = FileCheck2;
    headline = "Signed and stored";
    detail =
      errors > 0
        ? `Signed with ${errors} ${plural(errors, "error")} outstanding, recorded as an override. Download it below.`
        : "The carrier signature has been stamped. Download it below.";
  } else if (errors > 0) {
    tone = "danger";
    Icon = AlertTriangle;
    headline = `${errors} ${plural(errors, "error")}`;
    if (pages.length > 0) headline += ` · fix ${pageList(pages)}`;
    detail =
      pages.length > 0
        ? "Send the note below to the driver, then upload the corrected contract."
        : "Send the note below to the driver.";
    if (warnings > 0) {
      detail += ` ${warnings} ${plural(warnings, "warning")} to look at as well.`;
    }
  } else {
    tone = "success";
    Icon = CheckCircle2;
    headline = "Nothing to fix";
    detail =
      warnings > 0
        ? `No errors. ${warnings} ${plural(warnings, "warning")} worth a look, but nothing blocking.`
        : "Every required field is present and every check passed.";
  }

  return (
    <section
      aria-label="Verdict"
      className={cn(
        "rounded-lg border px-4 py-3.5",
        tone === "danger" && "border-danger-border bg-danger-muted",
        tone === "success" && "border-success-border bg-success-muted",
        tone === "neutral" && "border-border bg-card",
      )}
    >
      <div className="flex items-start gap-3">
        <Icon
          className={cn(
            "mt-0.5 size-5 shrink-0",
            tone === "danger" && "text-danger",
            tone === "success" && "text-success",
            tone === "neutral" && "text-muted-foreground",
          )}
          aria-hidden
        />
        <div>
          <h2
            className={cn(
              "text-base font-semibold tracking-tight",
              tone === "danger" && "text-danger",
              tone === "success" && "text-success",
            )}
          >
            {headline}
          </h2>
          <p className="mt-0.5 text-sm text-muted-foreground">{detail}</p>
        </div>
      </div>
    </section>
  );
}
