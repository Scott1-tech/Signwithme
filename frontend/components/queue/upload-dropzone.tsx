"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, Loader2, TriangleAlert } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError, contractsApi, signaturesApi, templatesApi } from "@/lib/api";
import { cn } from "@/lib/utils";

type Phase = "idle" | "uploading" | "reading";

const NONE = "__none__";

function today(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

/**
 * Upload, and say how it should be signed.
 *
 * The three choices are the heart of the app: which completed contract to
 * copy the placement from, whose signature to stamp, and what date to write.
 */
export function UploadDropzone() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const inputRef = React.useRef<HTMLInputElement>(null);

  const [dragging, setDragging] = React.useState(false);
  const [phase, setPhase] = React.useState<Phase>("idle");
  const [percent, setPercent] = React.useState(0);
  const [filename, setFilename] = React.useState("");

  const [templateId, setTemplateId] = React.useState<string>(NONE);
  const [signatureId, setSignatureId] = React.useState<string>(NONE);
  const [signDate, setSignDate] = React.useState<string>(today());

  const { data: templates } = useQuery({
    queryKey: ["templates"],
    queryFn: () => templatesApi.list(),
  });
  const { data: signatures } = useQuery({
    queryKey: ["signatures"],
    queryFn: () => signaturesApi.list(),
  });

  const usable = React.useMemo(
    () => (templates ?? []).filter((template) => template.ready),
    [templates],
  );

  // Sensible starting choices: the only template, and the default signature.
  React.useEffect(() => {
    if (templateId === NONE && usable.length === 1) setTemplateId(usable[0].id);
  }, [usable, templateId]);

  React.useEffect(() => {
    if (signatureId !== NONE) return;
    const fallback =
      signatures?.find((entry) => entry.is_default) ?? signatures?.[0];
    if (fallback) setSignatureId(fallback.id);
  }, [signatures, signatureId]);

  const upload = useMutation({
    mutationFn: (file: File) => {
      setFilename(file.name);
      setPhase("uploading");
      setPercent(0);
      return contractsApi.upload(
        file,
        (value) => {
          setPercent(value);
          if (value >= 100) setPhase("reading");
        },
        {
          templateId: templateId === NONE ? undefined : templateId,
          signatureId: signatureId === NONE ? undefined : signatureId,
          signDate: signDate || undefined,
        },
      );
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
  const nothingSetUp = usable.length === 0 || (signatures ?? []).length === 0;

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      {/* --- how it will be signed --- */}
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="grid gap-2">
          <Label htmlFor="upload-template">Template</Label>
          <Select value={templateId} onValueChange={setTemplateId}>
            <SelectTrigger id="upload-template">
              <SelectValue placeholder="Choose a template" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>No template — review only</SelectItem>
              {usable.map((template) => (
                <SelectItem key={template.id} value={template.id}>
                  {template.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid gap-2">
          <Label htmlFor="upload-signature">Signature</Label>
          <Select value={signatureId} onValueChange={setSignatureId}>
            <SelectTrigger id="upload-signature">
              <SelectValue placeholder="Choose a signature" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>No signature yet</SelectItem>
              {(signatures ?? []).map((asset) => (
                <SelectItem key={asset.id} value={asset.id}>
                  {asset.name}
                  {asset.is_default ? " (default)" : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid gap-2">
          <Label htmlFor="upload-date">Date to stamp</Label>
          <Input
            id="upload-date"
            type="date"
            value={signDate}
            onChange={(event) => setSignDate(event.target.value)}
          />
        </div>
      </div>

      {nothingSetUp && (
        <p className="flex items-start gap-2 rounded-md border border-warning-border bg-warning-muted px-3 py-2 text-xs">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden />
          <span className="text-muted-foreground">
            {usable.length === 0 && (
              <>
                No template is ready yet —{" "}
                <Link href="/templates" className="underline underline-offset-4">
                  create one from a contract you have already signed
                </Link>
                .{" "}
              </>
            )}
            {(signatures ?? []).length === 0 && (
              <>
                No signature saved —{" "}
                <Link href="/signatures" className="underline underline-offset-4">
                  add one
                </Link>
                .{" "}
              </>
            )}
            You can still upload a contract to check it; it just cannot be
            signed yet.
          </span>
        </p>
      )}

      {/* --- the file --- */}
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
          "rounded-lg border border-dashed border-border px-4 py-5 transition-colors",
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
                  Drop the PDF you downloaded from DocuSign here, or choose a
                  file.
                </p>
              </div>
            </div>
            <Button variant="outline" onClick={() => inputRef.current?.click()}>
              Choose PDF
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
