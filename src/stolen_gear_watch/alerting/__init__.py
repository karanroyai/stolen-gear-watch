import logging

from stolen_gear_watch.alerting.base import Notifier

__all__ = ["Notifier", "get_notifiers"]

logger = logging.getLogger(__name__)


def get_notifiers(settings) -> list[Notifier]:
    notifiers: list[Notifier] = []
    if settings.alerting.telegram.enabled:
        from stolen_gear_watch.alerting.telegram import TelegramNotifier

        try:
            notifiers.append(TelegramNotifier())
        except Exception:
            # Construction shouldn't normally raise (see TelegramNotifier's
            # own deferred-credential-loading comment), but this call site
            # is outside pipeline.py's per-item try/except, so a future
            # notifier that doesn't follow that lesson would otherwise
            # crash the entire scheduled run instead of just alerting.
            logger.exception("Failed to construct TelegramNotifier - alerting disabled this run")
    return notifiers
