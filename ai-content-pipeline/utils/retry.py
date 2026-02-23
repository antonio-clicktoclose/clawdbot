"""
Retry helper with exponential backoff.
"""

import asyncio
import functools
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger("pipeline.retry")

T = TypeVar("T")


async def retry_async(
    func: Callable[..., Any],
    *args: Any,
    max_attempts: int = 3,
    delays: tuple[float, ...] = (2.0, 4.0, 8.0),
    **kwargs: Any,
) -> Any:
    """Call an async callable with retries and exponential backoff.

    Returns the result on success or None after all attempts are exhausted.
    """
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                delay = delays[min(attempt, len(delays) - 1)]
                logger.warning(
                    "Attempt %d/%d failed for %s: %s — retrying in %.1fs",
                    attempt + 1,
                    max_attempts,
                    getattr(func, "__name__", str(func)),
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "All %d attempts failed for %s: %s",
                    max_attempts,
                    getattr(func, "__name__", str(func)),
                    exc,
                )
    return None


def retry_sync(
    func: Callable[..., Any],
    *args: Any,
    max_attempts: int = 3,
    delays: tuple[float, ...] = (2.0, 4.0, 8.0),
    **kwargs: Any,
) -> Any:
    """Synchronous retry with exponential backoff."""
    import time

    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                delay = delays[min(attempt, len(delays) - 1)]
                logger.warning(
                    "Attempt %d/%d failed for %s: %s — retrying in %.1fs",
                    attempt + 1,
                    max_attempts,
                    getattr(func, "__name__", str(func)),
                    exc,
                    delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "All %d attempts failed for %s: %s",
                    max_attempts,
                    getattr(func, "__name__", str(func)),
                    exc,
                )
    return None
