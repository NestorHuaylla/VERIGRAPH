export type NotificationDeliveryChannel = "email" | "slack" | "webhook";
export type NotificationDeliveryStatus = "pending" | "sent" | "failed";
export type NotificationSeverity = "info" | "warning" | "critical";

export type NotificationDeliveryChannelMetrics = {
  channel: NotificationDeliveryChannel;
  total: number;
  pending: number;
  scheduled: number;
  sent: number;
  failed: number;
};

export type LastFailedNotificationDelivery = {
  id: string;
  notification_id: string;
  channel: NotificationDeliveryChannel;
  destination: string | null;
  attempts: number;
  last_error: string | null;
  status: NotificationDeliveryStatus;
  next_attempt_at: string | null;
  created_at: string;
};

export type NotificationMetricsResponse = {
  notifications_total: number;
  notifications_unread: number;
  notifications_by_severity: Record<string, number>;
  deliveries_total: number;
  deliveries_pending: number;
  deliveries_scheduled: number;
  deliveries_due: number;
  deliveries_sent: number;
  deliveries_failed: number;
  deliveries_by_channel: NotificationDeliveryChannelMetrics[];
  last_failed_delivery: LastFailedNotificationDelivery | null;
};

export type NotificationDeliveryListItem = {
  id: string;
  notification_id: string;
  channel: NotificationDeliveryChannel;
  destination: string | null;
  status: NotificationDeliveryStatus;
  attempts: number;
  last_error: string | null;
  sent_at: string | null;
  next_attempt_at: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string | null;
};

export type NotificationDeliveryStatusPayload = {
  status: NotificationDeliveryStatus;
  error?: string | null;
};

export type DashboardData = {
  metrics: NotificationMetricsResponse;
  deliveries: NotificationDeliveryListItem[];
};

export const demoDashboardData: DashboardData = {
  metrics: {
    notifications_total: 42,
    notifications_unread: 7,
    notifications_by_severity: {
      info: 10,
      warning: 24,
      critical: 8
    },
    deliveries_total: 18,
    deliveries_pending: 5,
    deliveries_scheduled: 3,
    deliveries_due: 2,
    deliveries_sent: 10,
    deliveries_failed: 3,
    deliveries_by_channel: [
      { channel: "webhook", total: 11, pending: 4, scheduled: 2, sent: 4, failed: 1 },
      { channel: "email", total: 4, pending: 1, scheduled: 1, sent: 2, failed: 0 },
      { channel: "slack", total: 3, pending: 0, scheduled: 0, sent: 2, failed: 1 }
    ],
    last_failed_delivery: {
      id: "demo-delivery-1",
      notification_id: "demo-notification-1",
      channel: "webhook",
      destination: "https://example.test/webhook",
      attempts: 3,
      last_error: "Webhook returned HTTP 500: server error",
      status: "failed",
      next_attempt_at: null,
      created_at: "2026-05-27T10:00:00Z"
    }
  },
  deliveries: [
    {
      id: "del-001",
      notification_id: "not-001",
      channel: "webhook",
      destination: "https://hooks.example.test/verigraph",
      status: "pending",
      attempts: 1,
      last_error: "Webhook returned HTTP 500: server error",
      sent_at: null,
      next_attempt_at: "2026-05-27T10:10:00Z",
      metadata: {
        notification_event_type: "report.high_risk",
        notification_severity: "warning",
        notification_title: "Reporte de alto riesgo recibido",
        notification_message: "El reporte quedo en nivel high con score 22.",
        route: "default",
        delivery_engine: "outbox"
      },
      created_at: "2026-05-27T10:00:00Z",
      updated_at: "2026-05-27T10:01:00Z"
    },
    {
      id: "del-002",
      notification_id: "not-002",
      channel: "email",
      destination: "alerts@verigraph.local",
      status: "sent",
      attempts: 0,
      last_error: null,
      sent_at: "2026-05-27T09:58:00Z",
      next_attempt_at: null,
      metadata: {
        notification_event_type: "appeal.created",
        notification_severity: "warning"
      },
      created_at: "2026-05-27T09:57:00Z",
      updated_at: "2026-05-27T09:58:00Z"
    },
    {
      id: "del-003",
      notification_id: "not-003",
      channel: "slack",
      destination: "#fraude-alertas",
      status: "failed",
      attempts: 3,
      last_error: "Unsupported delivery channel: slack",
      sent_at: null,
      next_attempt_at: null,
      metadata: {
        notification_event_type: "evidence.analysis_completed",
        notification_severity: "warning"
      },
      created_at: "2026-05-27T09:45:00Z",
      updated_at: "2026-05-27T09:52:00Z"
    }
  ]
};

export function filterDeliveries(
  deliveries: NotificationDeliveryListItem[],
  status: NotificationDeliveryStatus | "all",
  channel: NotificationDeliveryChannel | "all"
): NotificationDeliveryListItem[] {
  return deliveries.filter((delivery) => {
    if (status !== "all" && delivery.status !== status) {
      return false;
    }
    if (channel !== "all" && delivery.channel !== channel) {
      return false;
    }
    return true;
  });
}

export function formatMetricValue(value: number): string {
  return new Intl.NumberFormat("es-PE").format(value);
}
