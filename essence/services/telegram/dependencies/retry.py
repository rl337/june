"""Retry logic with exponential backoff for service calls."""
import asyncio
import logging
import grpc
import httpx
from typing import Callable, TypeVar, Optional, List
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Retryable gRPC error codes
RETRYABLE_GRPC_ERRORS = [
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
    grpc.StatusCode.RESOURCE_EXHAUSTED,
    grpc.StatusCode.ABORTED,
    grpc.StatusCode.INTERNAL,
    grpc.StatusCode.UNKNOWN
]

# Non-retryable gRPC error codes
NON_RETRYABLE_GRPC_ERRORS = [
    grpc.StatusCode.INVALID_ARGUMENT,
    grpc.StatusCode.NOT_FOUND,
    grpc.StatusCode.ALREADY_EXISTS,
    grpc.StatusCode.PERMISSION_DENIED,
    grpc.StatusCode.FAILED_PRECONDITION,
    grpc.StatusCode.OUT_OF_RANGE,
    grpc.StatusCode.UNIMPLEMENTED,
    grpc.StatusCode.UNAUTHENTICATED
]

# Retryable HTTP status codes
RETRYABLE_HTTP_STATUSES = [429, 500, 502, 503, 504]

# Non-retryable HTTP status codes
NON_RETRYABLE_HTTP_STATUSES = [400, 401, 403, 404, 405, 409, 422]


def is_retryable_grpc_error(error: Exception) -> bool:
    """Check if gRPC error is retryable."""
    import grpc
    if isinstance(error, grpc.RpcError):
        return error.code() in RETRYABLE_GRPC_ERRORS
    return False


def is_retryable_http_error(status_code: int) -> bool:
    """Check if HTTP status code is retryable."""
    return status_code in RETRYABLE_HTTP_STATUSES


def is_non_retryable_grpc_error(error: Exception) -> bool:
    """Check if gRPC error is non-retryable."""
    import grpc
    if isinstance(error, grpc.RpcError):
        return error.code() in NON_RETRYABLE_GRPC_ERRORS
    return False


def is_non_retryable_http_error(status_code: int) -> bool:
    """Check if HTTP status code is non-retryable."""
    return status_code in NON_RETRYABLE_HTTP_STATUSES


async def retry_with_exponential_backoff(
    func: Callable[..., T],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_errors: Optional[List] = None,
    non_retryable_errors: Optional[List] = None,
    *args,
    **kwargs
) -> T:
    """Retry function with exponential backoff.
    
    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        jitter: Add random jitter to delays
        retryable_errors: List of retryable error types/codes
        non_retryable_errors: List of non-retryable error types/codes
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func
    
    Returns:
        Result from func
    
    Raises:
        Last exception if all retries fail
    """
    import random
    
    last_exception = None
    delay = initial_delay
    
    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            
            # Check if error is non-retryable
            if non_retryable_errors:
                for non_retryable in non_retryable_errors:
                    if isinstance(e, non_retryable):
                        logger.debug(f"Non-retryable error: {e}")
                        raise
            
            # Check gRPC errors
            if isinstance(e, grpc.RpcError):
                if is_non_retryable_grpc_error(e):
                    logger.debug(f"Non-retryable gRPC error: {e.code()}")
                    raise
                if not is_retryable_grpc_error(e):
                    logger.debug(f"Non-retryable gRPC error: {e.code()}")
                    raise
            
            # Check HTTP errors (for httpx)
            if isinstance(e, httpx.HTTPStatusError):
                status_code = e.response.status_code
                if is_non_retryable_http_error(status_code):
                    logger.debug(f"Non-retryable HTTP error: {status_code}")
                    raise
                if not is_retryable_http_error(status_code):
                    logger.debug(f"Non-retryable HTTP error: {status_code}")
                    raise
            
            # Check retryable errors list
            if retryable_errors:
                is_retryable = False
                for retryable in retryable_errors:
                    if isinstance(e, retryable):
                        is_retryable = True
                        break
                if not is_retryable:
                    logger.debug(f"Error not in retryable list: {type(e).__name__}")
                    raise
            
            # If this was the last attempt, raise the exception
            if attempt >= max_retries:
                logger.error(f"Max retries ({max_retries}) exceeded for {func.__name__}: {e}")
                raise
            
            # Calculate delay with exponential backoff
            delay = min(initial_delay * (exponential_base ** attempt), max_delay)
            
            # Add jitter if enabled
            if jitter:
                jitter_amount = delay * 0.1 * random.random()  # 10% jitter
                delay = delay + jitter_amount
            
            # Log retry attempt
            logger.warning(
                f"Retry attempt {attempt + 1}/{max_retries} for {func.__name__} "
                f"after {delay:.2f}s: {e}"
            )
            
            # Wait before retrying
            await asyncio.sleep(delay)
    
    # Should never reach here, but just in case
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry logic failed unexpectedly")


def retry_async(max_retries: int = 3, initial_delay: float = 1.0, **kwargs):
    """Decorator for retrying async functions with exponential backoff.
    
    Usage:
        @retry_async(max_retries=3, initial_delay=1.0)
        async def my_function():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **func_kwargs):
            return await retry_with_exponential_backoff(
                func,
                max_retries=max_retries,
                initial_delay=initial_delay,
                *args,
                **kwargs,
                **func_kwargs
            )
        return wrapper
    return decorator
