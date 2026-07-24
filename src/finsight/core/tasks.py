"""Background task runner + retry decorator.

The UI must never freeze: anything that touches a database, a file, or
the network runs through ``TaskRunner.submit`` on a worker thread, and
results are marshalled back via callbacks. ``retry`` gives transient
operations (SMTP, network DBs) exponential backoff.
"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def retry(
    exceptions: tuple[type[BaseException], ...],
    attempts: int = 3,
    delay: float = 0.5,
    backoff: float = 2.0,
) -> Callable[[F], F]:
    """Retry transient failures with exponential backoff."""
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            wait = delay
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == attempts:
                        raise
                    logger.warning(
                        "%s failed (%d/%d): %s — retrying in %.1fs",
                        func.__qualname__,
                        attempt,
                        attempts,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
                    wait *= backoff
            raise AssertionError("unreachable")  # pragma: no cover

        return wrapper  # type: ignore[return-value]

    return decorator


class TaskRunner:
    """Small thread-pool wrapper with success/error callbacks.

    Callbacks receive the result/exception; the UI layer wraps them with
    ``widget.after(...)`` to hop back onto the Tk main thread.
    """

    def __init__(self, max_workers: int = 4) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="finsight")

    def submit(
        self,
        func: Callable[..., Any],
        *args: Any,
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        **kwargs: Any,
    ) -> Future:
        future = self._pool.submit(func, *args, **kwargs)

        def _finished(f: Future) -> None:
            exc = f.exception()
            if exc is not None:
                logger.error("background task %s failed: %s", func.__name__, exc)
                if on_error is not None:
                    on_error(exc)
            elif on_done is not None:
                on_done(f.result())

        future.add_done_callback(_finished)
        return future

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
