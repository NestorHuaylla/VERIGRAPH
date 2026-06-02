import { DashboardClient } from "@/components/dashboard-client";
import { InternalRouteGuard } from "@/components/internal-route-guard";

export default function DashboardPage() {
  return (
    <InternalRouteGuard allowedRoles={["admin", "analyst", "legal"]} title="Panel operativo">
      <DashboardClient />
    </InternalRouteGuard>
  );
}
