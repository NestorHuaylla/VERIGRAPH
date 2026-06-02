from worker.celery_app import celery_app
from worker.services.text_patterns import extract_text_signals


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def analyze_report_text(self, report_id: str, text: str) -> dict:
    return {
        "report_id": report_id,
        "signals": extract_text_signals(text),
    }


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def recalculate_graph_score(self, entity_id: str) -> dict:
    return {
        "entity_id": entity_id,
        "status": "queued_for_graph_score",
    }

