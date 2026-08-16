"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, ImageUp, Loader2, Save } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { configApi, contractsApi } from "@/lib/api";
import { pageList } from "@/lib/format";
import type { CarrierConfig, SignatureConfig } from "@/lib/types";

const DEFAULT_TYPE = "owner_operator_plan_a";

export function SignatureSettings() {
  const queryClient = useQueryClient();
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [signatureVersion, setSignatureVersion] = React.useState(0);
  const [placement, setPlacement] = React.useState<SignatureConfig | null>(null);
  const [contractId, setContractId] = React.useState<string>("");
  const [preview, setPreview] = React.useState<{ url: string; pages: number[] } | null>(
    null,
  );

  const { data: carrier, isPending } = useQuery({
    queryKey: ["carrier"],
    queryFn: () => configApi.getCarrier(),
  });

  // A few recent contracts to preview the placement against.
  const { data: contracts } = useQuery({
    queryKey: ["contracts", { page_size: 20 }],
    queryFn: () => contractsApi.list({ page_size: 20 }),
  });

  React.useEffect(() => {
    if (carrier && !placement) {
      setPlacement(
        carrier.placements[DEFAULT_TYPE] ??
          Object.values(carrier.placements)[0] ??
          null,
      );
    }
  }, [carrier, placement]);

  React.useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview.url);
    };
  }, [preview]);

  const uploadSignature = useMutation({
    mutationFn: (file: File) => configApi.uploadSignature(file),
    onSuccess: (updated) => {
      queryClient.setQueryData(["carrier"], updated);
      setSignatureVersion((value) => value + 1);
      toast.success("Signature image saved");
    },
    onError: (error) =>
      toast.error("Could not upload the signature", {
        description: error instanceof Error ? error.message : String(error),
      }),
  });

  const savePlacement = useMutation({
    mutationFn: () => {
      if (!carrier || !placement) throw new Error("Nothing to save");
      const next: CarrierConfig = {
        ...carrier,
        placements: { ...carrier.placements, [DEFAULT_TYPE]: placement },
      };
      return configApi.putCarrier(next);
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(["carrier"], updated);
      toast.success("Signature placement saved");
    },
    onError: (error) =>
      toast.error("Could not save the placement", {
        description: error instanceof Error ? error.message : String(error),
      }),
  });

  const testPlacement = useMutation({
    mutationFn: () => {
      if (!placement) throw new Error("No placement configured");
      if (!contractId) throw new Error("Choose a contract to preview against");
      return configApi.testPlacement(contractId, placement);
    },
    onSuccess: (result) => {
      setPreview((current) => {
        if (current) URL.revokeObjectURL(current.url);
        return { url: result.url, pages: result.pages };
      });
    },
    onError: (error) =>
      toast.error("No preview", {
        description: error instanceof Error ? error.message : String(error),
      }),
  });

  if (isPending || !carrier) return <Skeleton className="h-64 w-full" />;
  if (!placement) return null;

  const patch = (changes: Partial<SignatureConfig>) =>
    setPlacement((current) => (current ? { ...current, ...changes } : current));

  return (
    <div className="space-y-5">
      {/* --- The image --- */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">Signature image</h3>
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex h-20 w-52 items-center justify-center rounded-md border border-border bg-muted">
            {carrier.signature_uploaded ? (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                src={`${configApi.signatureUrl()}?v=${signatureVersion}`}
                alt="The configured carrier signature"
                className="max-h-full max-w-full object-contain"
              />
            ) : (
              <span className="text-xs text-muted-foreground">Nothing uploaded</span>
            )}
          </div>

          <div>
            <input
              ref={fileRef}
              type="file"
              accept="image/png,.png"
              className="sr-only"
              aria-label="Upload the carrier signature PNG"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) uploadSignature.mutate(file);
                event.target.value = "";
              }}
            />
            <Button
              variant="outline"
              onClick={() => fileRef.current?.click()}
              disabled={uploadSignature.isPending}
            >
              {uploadSignature.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <ImageUp aria-hidden />
              )}
              {carrier.signature_uploaded ? "Replace image" : "Upload PNG"}
            </Button>
            <p className="mt-1.5 text-xs text-muted-foreground">
              PNG only. A transparent background stamps most cleanly.
            </p>
          </div>
        </div>
      </div>

      {/* --- Placement --- */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold">Placement</h3>

        <div className="grid gap-2 sm:max-w-xs">
          <Label htmlFor="placement-mode">Mode</Label>
          <Select
            value={placement.mode}
            onValueChange={(value) =>
              patch({ mode: value as SignatureConfig["mode"] })
            }
          >
            <SelectTrigger id="placement-mode">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="anchor">Anchor — find a phrase</SelectItem>
              <SelectItem value="offset">Offset — fixed position</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            {placement.mode === "anchor"
              ? "Searches every page for a phrase and stamps relative to it. Survives page shifts between contract versions."
              : "A fixed spot, as a fraction of the page, so letter and legal both work."}
          </p>
        </div>

        {placement.mode === "anchor" ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Search phrase" htmlFor="anchor-phrase" className="sm:col-span-2">
              <Input
                id="anchor-phrase"
                value={placement.anchor_phrase}
                onChange={(event) => patch({ anchor_phrase: event.target.value })}
              />
            </Field>
            <NumberField
              label="Offset x (pt)"
              value={placement.dx}
              onChange={(dx) => patch({ dx })}
            />
            <NumberField
              label="Offset y (pt)"
              value={placement.dy}
              onChange={(dy) => patch({ dy })}
            />
            <label className="flex items-center gap-2 text-xs sm:col-span-2">
              <Checkbox
                checked={placement.fallback_to_offset}
                onCheckedChange={(value) =>
                  patch({ fallback_to_offset: value === true })
                }
              />
              Fall back to a fixed position when the phrase is not found
            </label>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="offset-x">
                Across the page — {Math.round(placement.offset_x_frac * 100)}%
              </Label>
              <Slider
                id="offset-x"
                value={[placement.offset_x_frac * 100]}
                min={0}
                max={100}
                step={1}
                onValueChange={([value]) => patch({ offset_x_frac: value / 100 })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="offset-y">
                Down the page — {Math.round(placement.offset_y_frac * 100)}%
              </Label>
              <Slider
                id="offset-y"
                value={[placement.offset_y_frac * 100]}
                min={0}
                max={100}
                step={1}
                onValueChange={([value]) => patch({ offset_y_frac: value / 100 })}
              />
            </div>
            <Field label="Pages (comma separated, -1 is the last page)" htmlFor="offset-pages" className="sm:col-span-2">
              <Input
                id="offset-pages"
                value={placement.offset_pages.join(", ")}
                onChange={(event) =>
                  patch({
                    offset_pages: event.target.value
                      .split(",")
                      .map((value) => Number(value.trim()))
                      .filter((value) => Number.isFinite(value) && value !== 0),
                  })
                }
              />
            </Field>
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <NumberField
            label="Width (pt)"
            value={placement.width}
            onChange={(width) => patch({ width })}
          />
          <NumberField
            label="Height (pt)"
            value={placement.height}
            onChange={(height) => patch({ height })}
          />
          <NumberField
            label="Date offset x (pt)"
            value={placement.date_dx}
            onChange={(date_dx) => patch({ date_dx })}
          />
          <NumberField
            label="Date offset y (pt)"
            value={placement.date_dy}
            onChange={(date_dy) => patch({ date_dy })}
          />
        </div>

        <label className="flex items-center gap-2 text-xs">
          <Checkbox
            checked={placement.stamp_date}
            onCheckedChange={(value) => patch({ stamp_date: value === true })}
          />
          Stamp the date beside the signature
        </label>
      </div>

      {/* --- Live preview --- */}
      <div className="space-y-3 rounded-lg border border-border bg-card p-3">
        <h4 className="text-sm font-semibold">Try it against a real contract</h4>

        <div className="flex flex-wrap items-end gap-2">
          <div className="grid gap-2 sm:min-w-72">
            <Label htmlFor="preview-contract">Contract</Label>
            <Select value={contractId} onValueChange={setContractId}>
              <SelectTrigger id="preview-contract">
                <SelectValue placeholder="Choose an uploaded contract" />
              </SelectTrigger>
              <SelectContent>
                {(contracts?.items ?? []).map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {item.driver_name ?? item.original_filename}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Button
            variant="outline"
            onClick={() => testPlacement.mutate()}
            disabled={!contractId || testPlacement.isPending}
          >
            {testPlacement.isPending ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <Eye aria-hidden />
            )}
            Preview placement
          </Button>

          <Button
            className="ml-auto"
            onClick={() => savePlacement.mutate()}
            disabled={savePlacement.isPending}
          >
            {savePlacement.isPending ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <Save aria-hidden />
            )}
            Save placement
          </Button>
        </div>

        {(contracts?.items?.length ?? 0) === 0 && (
          <p className="text-xs text-muted-foreground">
            Upload a contract on the queue screen first, then preview against it.
          </p>
        )}

        {preview && (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">
              Red box shows where the signature lands. Matched{" "}
              {preview.pages.length > 0 ? pageList(preview.pages) : "nothing"}.
            </p>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={preview.url}
              alt="Preview of the page with the signature placement drawn"
              className="mx-auto block h-auto w-full max-w-[760px] rounded-md border border-border"
            />
          </div>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  htmlFor,
  className,
  children,
}: {
  label: string;
  htmlFor: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={`grid gap-2 ${className ?? ""}`}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  const id = React.useId();
  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="number"
        value={value}
        onChange={(event) => {
          const next = Number(event.target.value);
          if (Number.isFinite(next)) onChange(next);
        }}
        className="tabular-nums"
      />
    </div>
  );
}
