"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, RotateCcw, Save } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { configApi } from "@/lib/api";
import type { FieldMap, FieldSpec } from "@/lib/types";

/**
 * Where day one is spent. Canonical field keys are fixed — the rules engine
 * looks them up by name — so the key column is read-only and the editable
 * parts are the label, the AcroForm name, and the text anchors.
 */
export function FieldMapEditor() {
  const queryClient = useQueryClient();
  const [draft, setDraft] = React.useState<FieldMap | null>(null);
  const [contractType, setContractType] = React.useState<string | null>(null);

  const { data, isPending, isError, error } = useQuery({
    queryKey: ["field-map"],
    queryFn: () => configApi.getFields(),
  });

  React.useEffect(() => {
    if (data && !draft) {
      setDraft(data);
      setContractType(Object.keys(data.contract_types)[0] ?? null);
    }
  }, [data, draft]);

  const save = useMutation({
    mutationFn: (map: FieldMap) => configApi.putFields(map),
    onSuccess: (saved) => {
      setDraft(saved);
      queryClient.setQueryData(["field-map"], saved);
      toast.success("Field map saved");
    },
    onError: (mutationError) =>
      toast.error("Could not save the field map", {
        description:
          mutationError instanceof Error ? mutationError.message : String(mutationError),
      }),
  });

  const reset = useMutation({
    mutationFn: () => configApi.resetFields(),
    onSuccess: (saved) => {
      setDraft(saved);
      setContractType(Object.keys(saved.contract_types)[0] ?? null);
      queryClient.setQueryData(["field-map"], saved);
      toast.success("Field map restored to the defaults");
    },
    onError: (mutationError) =>
      toast.error("Could not reset the field map", {
        description:
          mutationError instanceof Error ? mutationError.message : String(mutationError),
      }),
  });

  if (isPending) return <Skeleton className="h-64 w-full" />;

  if (isError) {
    return (
      <p className="rounded-md border border-danger-border bg-danger-muted px-3 py-2 text-sm text-danger">
        Could not load the field map:{" "}
        {error instanceof Error ? error.message : "unknown error"}
      </p>
    );
  }

  if (!draft || !contractType) return null;

  const specs = draft.contract_types[contractType] ?? [];

  const update = (index: number, patch: Partial<FieldSpec>) => {
    setDraft((current) => {
      if (!current) return current;
      const next = { ...current.contract_types };
      const list = [...(next[contractType] ?? [])];
      list[index] = { ...list[index], ...patch };
      next[contractType] = list;
      return { contract_types: next };
    });
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Field mapping</h3>
          <p className="text-xs text-muted-foreground">
            Contract type <span className="font-mono">{contractType}</span>.
            The field key is fixed; change the label and the anchors to match
            the wording on your form.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => reset.mutate()}
            disabled={reset.isPending}
          >
            <RotateCcw aria-hidden />
            Restore defaults
          </Button>
          <Button
            size="sm"
            onClick={() => save.mutate(draft)}
            disabled={save.isPending}
          >
            {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Save aria-hidden />}
            Save field map
          </Button>
        </div>
      </div>

      <div className="rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-40">Field key</TableHead>
              <TableHead className="w-48">Label</TableHead>
              <TableHead className="w-40">AcroForm name</TableHead>
              <TableHead>Text anchors (comma separated)</TableHead>
              <TableHead className="w-20 text-center">Required</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {specs.map((spec, index) => (
              <TableRow key={spec.field_key}>
                <TableCell className="font-mono text-xs">{spec.field_key}</TableCell>
                <TableCell>
                  <Input
                    value={spec.label}
                    onChange={(event) => update(index, { label: event.target.value })}
                    aria-label={`Label for ${spec.field_key}`}
                    className="h-8"
                  />
                </TableCell>
                <TableCell>
                  <Input
                    value={spec.acroform_name ?? ""}
                    onChange={(event) =>
                      update(index, { acroform_name: event.target.value || null })
                    }
                    aria-label={`AcroForm name for ${spec.field_key}`}
                    className="h-8 font-mono text-xs"
                  />
                </TableCell>
                <TableCell>
                  <Input
                    value={spec.anchors.join(", ")}
                    onChange={(event) =>
                      update(index, {
                        anchors: event.target.value
                          .split(",")
                          .map((value) => value.trim())
                          .filter(Boolean),
                      })
                    }
                    aria-label={`Text anchors for ${spec.field_key}`}
                    className="h-8"
                  />
                </TableCell>
                <TableCell className="text-center">
                  <Checkbox
                    checked={spec.required}
                    onCheckedChange={(value) =>
                      update(index, { required: value === true })
                    }
                    aria-label={`${spec.field_key} is required`}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
