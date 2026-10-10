import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("devtracker")
# Lee las variables CELERY_* de settings.py
app.config_from_object("django.conf:settings", namespace="CELERY")
# Busca tasks.py en cada app instalada
app.autodiscover_tasks()
