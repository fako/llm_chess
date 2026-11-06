"""Exports the Celery app so `celery --app web` finds it."""
from web.celery import app as celery_app


__all__ = ["celery_app"]
