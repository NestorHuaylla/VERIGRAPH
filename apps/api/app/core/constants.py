from enum import StrEnum


class EntityType(StrEnum):
    URL = "url"
    DOMAIN = "domain"
    PHONE = "phone"
    EMAIL = "email"
    WALLET = "wallet"
    SOCIAL_PROFILE = "social_profile"
    SOCIAL_CHANNEL = "social_channel"
    BANK_ACCOUNT = "bank_account"
    OTHER = "other"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    SUSPECT = "suspect"
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    APPEAL = "appeal"
    ARCHIVED = "archived"


class AppealStatus(StrEnum):
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class CaseStatus(StrEnum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    ARCHIVED = "archived"


class NotificationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class NotificationDeliveryChannel(StrEnum):
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"


class NotificationDeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


MAX_NOTIFICATION_DELIVERY_ATTEMPTS = 3
NOTIFICATION_DELIVERY_BACKOFF_BASE_SECONDS = 60
NOTIFICATION_DELIVERY_BACKOFF_MAX_SECONDS = 3600


class UserRole(StrEnum):
    REPORTER = "reporter"
    ANALYST = "analyst"
    ADMIN = "admin"
    LEGAL = "legal"
