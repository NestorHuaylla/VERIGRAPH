import { CasesClient } from "@/components/cases-client";
import { InternalRouteGuard } from "@/components/internal-route-guard";

export default function CasesPage() {
  return (
    <InternalRouteGuard allowedRoles={["admin", "analyst", "legal"]} title="Expedientes">
      <CasesClient />
    </InternalRouteGuard>
  );
}
