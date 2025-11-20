"""
Utility functions used across the Telegram bot project.

This module centralises common helper functions such as logging
configuration and extracting file URLs from Telegram photo objects. Keeping
these helpers in a dedicated module helps avoid circular imports and
encourages reuse.
"""

from __future__ import annotations

import logging
from typing import Optional

from telegram import PhotoSize


def setup_logging(level: int = logging.INFO) -> None:
    """Configure Python's logging subsystem.

    Sets up a root logger with the given level and a simple log format. In
    production on Railway the platform will capture stdout/stderr so this
    configuration is sufficient. When running locally you will see
    timestamped logs with the log level and originating module.

    Args:
        level: Logging level to use for the root logger. Defaults to
            ``logging.INFO``.
    """
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=level,
    )


async def extract_image_url(photo: PhotoSize) -> str:
    """Obtain the publicly accessible file URL for a Telegram photo.

    This helper wraps the asynchronous call to ``PhotoSize.get_file`` and
    returns the ``file_path`` attribute which points at Telegram's CDN. The
    returned URL can be supplied directly to Higgsfield's API. If the
    photo object cannot be resolved an exception will be propagated to
    the caller.

    Args:
        photo: The highest resolution ``PhotoSize`` object provided by
            Telegram for an uploaded image.

    Returns:
        The file URL as a string.
    """
    tg_file = await photo.get_file()
    # ``file_path`` is a full URL hosted by Telegram which can be fetched by
    # third‑party services. In the rare case this attribute is missing
    # ``get_file()`` will raise instead.
    return tg_file.file_path