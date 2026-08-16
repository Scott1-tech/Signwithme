import { Suspense } from "react";

import { QueueScreen } from "@/components/queue/queue-screen";
import { Skeleton } from "@/components/ui/skeleton";

export default function QueuePage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <QueueScreen />
    </Suspense>
  );
}
