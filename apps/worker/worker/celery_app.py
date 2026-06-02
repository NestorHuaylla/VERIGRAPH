from celery import Celery

from worker.config import settings

celery_app = Celery(
    "verigraph_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "worker.tasks.external_checks",
        "worker.tasks.analysis",
        "worker.tasks.alerts",
    ],
)

celery_app.conf.task_routes = {
    "worker.tasks.external_checks.*": {"queue": "external_checks"},
    "worker.tasks.analysis.*": {"queue": "analysis"},
    "worker.tasks.alerts.*": {"queue": "alerts"},
}

celery_app.conf.task_default_retry_delay = 30
celery_app.conf.task_acks_late = True
celery_app.conf.worker_prefetch_multiplier = 1

