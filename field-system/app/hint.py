"""Officials' hints and the guards' big-fire flag must never take an alert list, card or brief down with them."""
import logging

log = logging.getLogger("hint")


def safe(fn, *a, default=None, **k):
    """fn(*a, **k), or `default` (logged) when it raises: a broken hint is left off the card, the alert is still shown."""
    try:
        return fn(*a, **k)
    except Exception:
        log.exception("hint %s failed", getattr(fn, "__qualname__", fn))
        return default
