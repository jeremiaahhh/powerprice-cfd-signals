from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "powerprice",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.jobs.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "ingest-data-hourly": {
            "task": "app.jobs.tasks.ingest_data",
            "schedule": 3600.0,  # every hour
        },
        "generate-signal-every-15min": {
            "task": "app.jobs.tasks.generate_and_cache_signal",
            "schedule": 900.0,  # every 15 minutes
        },
        "retrain-models-daily": {
            "task": "app.jobs.tasks.retrain_models",
            "schedule": 86400.0,  # daily
        },
        "check-paper-positions-every-5min": {
            "task": "app.jobs.tasks.check_paper_positions",
            "schedule": 300.0,
        },
    },
)
