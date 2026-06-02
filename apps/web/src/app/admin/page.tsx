import { AdminClient } from "@/components/admin-client";
import { InternalRouteGuard } from "@/components/internal-route-guard";

export default function AdminPage() {
  return (
    <InternalRouteGuard allowedRoles={["admin", "analyst", "legal"]} title="Panel admin">
      <AdminClient />
    </InternalRouteGuard>
  );
}
