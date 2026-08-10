from stolen_gear_watch.alerting.base import Notifier

__all__ = ["Notifier", "get_notifiers"]


def get_notifiers(settings) -> list[Notifier]:
    notifiers: list[Notifier] = []
    if settings.alerting.telegram.enabled:
        from stolen_gear_watch.alerting.telegram import TelegramNotifier

        notifiers.append(TelegramNotifier())
    return notifiers
