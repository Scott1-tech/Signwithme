import { DetailScreen } from "@/components/detail/detail-screen";

export default async function ContractPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <DetailScreen contractId={id} />;
}
