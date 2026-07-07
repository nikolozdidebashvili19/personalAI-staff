"""Desktop notifications — Windows toast via plyer, silent no-op elsewhere."""

from core.logger import get_logger

log = get_logger("notifications")


def notify(title: str, message: str) -> None:
    try:
        from plyer import notification

        notification.notify(title=title, message=message[:250], timeout=10)
    except Exception as e:
        log.info("Notification skipped: %s", e)
