"use client";

import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Loader2, Save } from "lucide-react";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { configApi } from "@/lib/api";

const schema = z.object({
  carrier_name: z.string().min(1, "The carrier name is required."),
  representative_name: z.string().min(1, "The representative name is required."),
  representative_title: z.string(),
  mc_number: z.string(),
  dot_number: z.string(),
});

type CompanyForm = z.infer<typeof schema>;

export function CompanyDetails() {
  const queryClient = useQueryClient();

  const { data: carrier, isPending } = useQuery({
    queryKey: ["carrier"],
    queryFn: () => configApi.getCarrier(),
  });

  const form = useForm<CompanyForm>({
    resolver: zodResolver(schema),
    values: carrier
      ? {
          carrier_name: carrier.carrier_name,
          representative_name: carrier.representative_name,
          representative_title: carrier.representative_title,
          mc_number: carrier.mc_number,
          dot_number: carrier.dot_number,
        }
      : undefined,
    defaultValues: {
      carrier_name: "",
      representative_name: "",
      representative_title: "",
      mc_number: "",
      dot_number: "",
    },
  });

  const save = useMutation({
    mutationFn: (values: CompanyForm) => {
      if (!carrier) throw new Error("Nothing to save");
      return configApi.putCarrier({ ...carrier, ...values });
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(["carrier"], updated);
      toast.success("Company details saved");
    },
    onError: (error) =>
      toast.error("Could not save the company details", {
        description: error instanceof Error ? error.message : String(error),
      }),
  });

  if (isPending) return <Skeleton className="h-52 w-full" />;

  const fields: Array<{ name: keyof CompanyForm; label: string; hint?: string }> = [
    { name: "carrier_name", label: "Carrier name" },
    { name: "representative_name", label: "Representative name" },
    { name: "representative_title", label: "Representative title" },
    { name: "mc_number", label: "MC number" },
    { name: "dot_number", label: "DOT number" },
  ];

  return (
    <form
      onSubmit={form.handleSubmit((values) => save.mutate(values))}
      className="space-y-4"
      noValidate
    >
      <div>
        <h3 className="text-sm font-semibold">Company details</h3>
        <p className="text-xs text-muted-foreground">
          Used to fill carrier-side fields when a contract is executed. The
          driver&apos;s own answers are never touched.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:max-w-3xl">
        {fields.map((field) => {
          const error = form.formState.errors[field.name];
          return (
            <div key={field.name} className="grid gap-2">
              <Label htmlFor={field.name}>{field.label}</Label>
              <Input
                id={field.name}
                {...form.register(field.name)}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? `${field.name}-error` : undefined}
              />
              {error && (
                <p id={`${field.name}-error`} className="text-xs text-danger">
                  {error.message}
                </p>
              )}
            </div>
          );
        })}
      </div>

      <Button type="submit" disabled={save.isPending}>
        {save.isPending ? (
          <Loader2 className="animate-spin" aria-hidden />
        ) : (
          <Save aria-hidden />
        )}
        Save company details
      </Button>
    </form>
  );
}
