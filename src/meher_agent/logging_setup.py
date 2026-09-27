"""Root logger setup with contact-detail masking applied to every record."""
from __future__ import annotations

import logging

from meher_agent.config import Settings, settings as default_settings
from meher_agent.privacy import MaskingFilter


def setup_logging(settings_obj: Settings | None = None) -> None:
    """Installs a masking filter on the root logger's handler(s).

    The filter is attached to handlers, not the logger itself: a logger's
    own filters only run for records it creates directly, while records
    from child loggers propagate straight to ancestor handlers -- so a
    logger-level filter here would miss most application log calls.
    """
    settings_obj = settings_obj or default_settings
    root = logging.getLogger()
    root.setLevel(settings_obj.logging.level)

    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)

    for handler in root.handlers:
        if not any(isinstance(f, MaskingFilter) for f in handler.filters):
            handler.addFilter(MaskingFilter())
