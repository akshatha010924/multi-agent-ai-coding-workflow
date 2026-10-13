import logging

from app.guardrails.patterns import redact


class RedactingFilter(logging.Filter):
    """Masks anything that looks like a secret before it reaches a log handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if getattr(root, "_mac_configured", False):
        root.setLevel(level.upper())
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    root.addHandler(handler)
    root.setLevel(level.upper())
    root._mac_configured = True  # type: ignore[attr-defined]
