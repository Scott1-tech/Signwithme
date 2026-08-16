"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileUp, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ApiError, contractsApi } from "@/lib/api";
import { cn } from "@/lib/utils";

type Phase = "idle" | "uploading" | "reading";

export function UploadDropzone() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const inputRef = React.useRef<HTMLInputElement>(null);

  const [dragging, setDragging] = React.useState(false);
  const [phase, setPhase] = React.useState<Phase>("idle");
  const [percent, setPercent] = React.useState(0);
  const [filename, setFilename] = React.useState("");

  const upload = useMutation({
    mutationFn: (file: File) => {
      setFilename(file.name);
      setPhase("uploading");
      setPercent(0);
      return contractsApi.upload(file, (value) => {
        setPercent(value);
        // The bytes are all sent; the server is now extracting and
        // validating, which is the part that actually takes seconds.
        if (value >= 100) setPhase("reading");
      });
    },
    onSuccess: (contract) => {
      setPhase("idle");
      queryClient.invalidateQueries({ queryKey: ["contracts"] });
      router.push(`/contracts/${contract.id}`);
    },
    onError: (error) => {
      setPhase("idle");
      if (error instanceof ApiError) {
        const duplicate = error.duplicate;
        if (duplicate) {
          toast.warning("This file has already been uploaded", {
            description: `Opened as ${duplicate.original_filename}.`,
            action: {
              label: "Open it",
              onClick: () => router.push(`/contracts/${duplicate.contract_id}`),
            },
            duration: 10_000,
          });
          return;
        }
        toast.error("Upload failed", { description: error.message });
        return;
      }
      toast.error("Upload failed", { description: String(error) });
    },
  });

  const handleFiles = React.useCallback(
    (files: FileList | null) => {
      const file = files?.[0];
      if (!file) return;
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        toast.error("That is not a PDF", {
          description:
            "Download the completed contract from DocuSign and upload the PDF.",
        });
        return;
      }
      upload.mutate(file);
    },
    [upload],
  );

  const busy = phase !== "idle";

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        if (!busy) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        if (!busy) handleFiles(event.dataTransfer.files);
      }}
      className={cn(
        "rounded-lg border border-dashed border-border bg-card px-4 py-5 transition-colors",
        dragging && "border-primary bg-accent",
        busy && "border-solid",
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        onChange={(event) => {
          handleFiles(event.target.files);
          event.target.value = "";
        }}
        aria-label="Upload a signed contract PDF"
      />

      {busy ? (
        <div className="space-y-2" aria-live="polite">
          <div className="flex items-center gap-2 text-sm">
            <Loader2 className="size-4 animate-spin" aria-hidden />
            <span className="font-medium">
              {phase === "uploading"
                ? `Uploading ${filename}…`
                : "Reading the contract and checking the rules…"}
            </span>
          </div>
          <Progress
            value={phase === "uploading" ? percent : undefined}
            className={phase === "reading" ? "animate-pulse" : undefined}
          />
          <p className="text-xs text-muted-foreground">
            {phase === "uploading"
              ? `${percent}% sent`
              : "A fifty-page contract takes a few seconds."}
          </p>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <FileUp className="size-5 text-muted-foreground" aria-hidden />
            <div>
              <p className="font-medium">Upload a signed contract</p>
              <p className="text-xs text-muted-foreground">
                Drop the PDF you downloaded from DocuSign here, or choose a file.
              </p>
            </div>
          </div>
          <Button variant="outline" onClick={() => inputRef.current?.click()}>
            Choose PDF
          </Button>
        </div>
      )}
    </div>
  );
}
