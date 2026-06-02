import { InternalRouteGuard } from "@/components/internal-route-guard";
import { UsersClient } from "@/components/users-client";

export default function UsersPage() {
  return (
    <InternalRouteGuard allowedRoles={["admin"]} title="Usuarios y roles">
      <UsersClient />
    </InternalRouteGuard>
  );
}
