from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "not_just_dark",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.email", "app.tasks.inventory", "app.tasks.orders"]
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,

    # Task execution settings
    task_acks_late=True,  # Acknowledge task after completion (safer)
    task_reject_on_worker_lost=True,
    task_time_limit=300,  # 5 minute hard limit
    task_soft_time_limit=240,  # 4 minute soft limit

    # Worker settings
    worker_prefetch_multiplier=4,  # Fetch 4 tasks per worker at a time
    worker_concurrency=4,  # Number of concurrent workers

    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour

    # Retry settings
    task_default_retry_delay=60,  # Retry after 60 seconds
    task_max_retries=3,

    # Rate limiting
    task_annotations={
        "app.tasks.email.*": {"rate_limit": "10/s"},  # Max 10 emails per second
        "app.tasks.inventory.*": {"rate_limit": "50/s"},
    },

    # Beat scheduler for periodic tasks
    beat_schedule={
        "check-low-stock": {
            "task": "app.tasks.inventory.check_low_stock",
            "schedule": 3600.0,  # Every hour
        },
        "cleanup-abandoned-carts": {
            "task": "app.tasks.orders.cleanup_abandoned_carts",
            "schedule": 86400.0,  # Every 24 hours
        },
        "release-expired-orders": {
            "task": "app.tasks.orders.release_expired_orders",
            "schedule": 300.0,
        },
        "sync-inventory-cache": {
            "task": "app.tasks.inventory.sync_inventory_cache",
            "schedule": 300.0,  # Every 5 minutes
        },
    },
)
