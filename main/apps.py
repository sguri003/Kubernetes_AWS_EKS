import logging
import os
import sys
import threading
import time
from pathlib import Path

from django.apps import AppConfig

logger = logging.getLogger(__name__)

REFRESH_CHECK_INTERVAL = 3600  # seconds — refresh_if_stale() itself no-ops until the date rolls over


class MainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'main'

    def ready(self):
        argv0 = Path(sys.argv[0]).stem.lower() if sys.argv else ""
        is_runserver = len(sys.argv) > 1 and sys.argv[1] == "runserver"
        is_gunicorn = argv0 == "gunicorn"
        if not (is_runserver or is_gunicorn):
            return
        if is_runserver and os.environ.get("RUN_MAIN") != "true":
            return  # skip the autoreloader's watcher process
        threading.Thread(target=_daily_refresh_loop, daemon=True).start()


def _daily_refresh_loop():
    import stocks
    while True:
        try:
            stocks.refresh_if_stale()
        except Exception:
            logger.exception("Daily price refresh failed")
        time.sleep(REFRESH_CHECK_INTERVAL)
