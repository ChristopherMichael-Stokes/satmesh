"""HTTP conventions shared by every satmesh source: User-Agent, status handling and retry."""

from collections.abc import Callable
from importlib.metadata import version

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

USER_AGENT = f"satmesh/{version('satmesh-data')} (research terrain-mesh tool)"
MAX_ATTEMPTS = 5
MAX_BACKOFF_S = 60.0
DEFAULT_INITIAL_BACKOFF_S = 2.0
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class RetryableStatusError(Exception):
    """A rate-limit or server-error status worth another attempt."""


def new_client() -> httpx.Client:
    """Return a client with the satmesh User-Agent and redirects followed."""
    return httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=120.0)


def checked(response: httpx.Response) -> httpx.Response:
    """Return `response` if it succeeded, else raise `RetryableStatusError` or `HTTPStatusError`."""
    if response.status_code in RETRYABLE_STATUS_CODES:
        msg = f"{response.status_code} from {response.request.url}"
        raise RetryableStatusError(msg)
    return response.raise_for_status()


def with_retry[T](attempt: Callable[[], T], initial_backoff_s: float) -> T:
    """Call `attempt` until it succeeds, backing off exponentially on network and retryable errors.

    Wait before retry n (n >= 1) is min(initial_backoff_s * 2**(n - 1), MAX_BACKOFF_S); after
    MAX_ATTEMPTS the last error propagates unchanged.
    """
    retrying = Retrying(
        stop=stop_after_attempt(MAX_ATTEMPTS),
        wait=wait_exponential(multiplier=initial_backoff_s, max=MAX_BACKOFF_S),
        retry=retry_if_exception_type((httpx.TransportError, RetryableStatusError)),
        reraise=True,
    )
    return retrying(attempt)
