from worker.celery_app import celery_app
from worker.services.alerts import send_alert


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_risk_alert(self, channel: str, title: str, message: str) -> dict:
    result = send_alert(channel=channel, title=title, message=message)
    if result.get("status") == "failed" and result.get("retryable"):
        raise RuntimeError(str(result.get("error") or "Alert delivery failed."))
    return result
