import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  CircleDashed,
  FileCheck2,
  History,
  PenLine,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { statusLabel } from "@/lib/format";
import type { ContractStatus } from "@/lib/types";

/**
 * Status is the primary scan target on the queue, so it never relies on
 * colour alone: every state pairs an icon with its label.
 */
const STATUS_STYLE: Record<
  ContractStatus,
  { variant: "default" | "outline" | "danger" | "warning" | "success"; Icon: typeof Ban }
> = {
  uploaded: { variant: "outline", Icon: CircleDashed },
  extracted: { variant: "outline", Icon: CircleDashed },
  needs_review: { variant: "danger", Icon: AlertTriangle },
  clean: { variant: "success", Icon: CheckCircle2 },
  approved: { variant: "default", Icon: PenLine },
  executed: { variant: "default", Icon: FileCheck2 },
  superseded: { variant: "outline", Icon: History },
  void: { variant: "outline", Icon: Ban },
};

export function StatusBadge({ status }: { status: ContractStatus }) {
  const { variant, Icon } = STATUS_STYLE[status] ?? STATUS_STYLE.uploaded;
  return (
    <Badge variant={variant}>
      <Icon className="size-3.5" aria-hidden />
      {statusLabel(status)}
    </Badge>
  );
}
