import { GraphClient } from "@/components/graph-client";
import { InternalRouteGuard } from "@/components/internal-route-guard";

export default function GraphPage() {
  return (
    <InternalRouteGuard allowedRoles={["admin", "analyst", "legal"]} title="Vista de grafo">
      <GraphClient />
    </InternalRouteGuard>
  );
}
