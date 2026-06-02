from worker.celery_app import celery_app
from worker.services.api_client import post_external_reputation_result
from worker.services.external_sources import check_external_reputation


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def check_url_reputation(self, entity_id: str, url: str) -> dict:
    result = check_external_reputation(entity_id=entity_id, value=url, entity_type="url")
    result["persistence"] = post_external_reputation_result(entity_id, result, task_id=self.request.id)
    return result


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def check_domain_reputation(self, entity_id: str, domain: str) -> dict:
    result = check_external_reputation(entity_id=entity_id, value=domain, entity_type="domain")
    result["persistence"] = post_external_reputation_result(entity_id, result, task_id=self.request.id)
    return result
