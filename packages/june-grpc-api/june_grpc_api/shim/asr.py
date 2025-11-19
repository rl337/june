import grpc
import logging
import asyncio
from typing import Optional

from ..generated import asr_pb2, asr_pb2_grpc

logger = logging.getLogger(__name__)


class STTError(Exception):
    """Base exception for STT client errors."""

    pass


class STTTimeoutError(STTError):
    """Raised when STT request times out."""

    pass


class STTConnectionError(STTError):
    """Raised when unable to connect to STT service."""

    pass


class STTServiceError(STTError):
    """Raised when STT service returns an error."""

    pass


class RecognitionResult:
    def __init__(
        self,
        transcript: str,
        confidence: float,
        is_final: bool = True,
        detected_language: Optional[str] = None,
    ):
        self.transcript = transcript
        self.confidence = confidence
        self.is_final = is_final
        self.detected_language = detected_language
        self.start_time_us = 0
        self.end_time_us = 0
        self.words = []


class RecognitionConfig:
    def __init__(self, language: str = "en", interim_results: bool = False):
        self.language = language
        self.interim_results = interim_results

    def to_proto(self) -> asr_pb2.RecognitionConfig:
        return asr_pb2.RecognitionConfig(
            language=self.language, interim_results=self.interim_results
        )


class SpeechToTextClient:
    """
    gRPC client for Speech-to-Text service.

    Handles errors and timeouts when communicating with the STT service.
    Implements automatic retry logic with exponential backoff for transient errors.
    """

    def __init__(
        self,
        channel: grpc.Channel,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        max_backoff: float = 10.0,
        backoff_multiplier: float = 2.0,
    ):
        """
        Initialize STT client.

        Args:
            channel: gRPC channel to the STT service
            max_retries: Maximum number of retry attempts for transient errors (default: 3)
            initial_backoff: Initial backoff delay in seconds (default: 1.0)
            max_backoff: Maximum backoff delay in seconds (default: 10.0)
            backoff_multiplier: Multiplier for exponential backoff (default: 2.0)
        """
        self._stub = asr_pb2_grpc.SpeechToTextStub(channel)
        self._channel = channel
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_multiplier = backoff_multiplier

    def _is_retryable_error(self, error_code: grpc.StatusCode) -> bool:
        """
        Check if an error code is retryable (transient error).

        Args:
            error_code: gRPC status code

        Returns:
            True if the error is retryable, False otherwise
        """
        # Retryable errors: network failures, temporary unavailability, timeouts
        retryable_codes = (
            grpc.StatusCode.UNAVAILABLE,  # Service unavailable
            grpc.StatusCode.DEADLINE_EXCEEDED,  # Request timeout (transient)
            grpc.StatusCode.RESOURCE_EXHAUSTED,  # Resource temporarily exhausted
            grpc.StatusCode.ABORTED,  # Operation aborted (may be retryable)
            grpc.StatusCode.INTERNAL,  # Internal server error (may be transient)
        )
        return error_code in retryable_codes

    async def recognize(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
        encoding: str = "wav",
        config: Optional[RecognitionConfig] = None,
        timeout: Optional[float] = 30.0,
    ) -> RecognitionResult:
        """
        Send audio to STT Recognize endpoint and extract transcribed text.

        Implements automatic retry logic with exponential backoff for transient errors.

        Args:
            audio_data: Raw audio data bytes
            sample_rate: Audio sample rate (default: 16000 Hz)
            encoding: Audio encoding format (default: "wav")
            config: Optional recognition configuration
            timeout: Request timeout in seconds (default: 30.0)

        Returns:
            RecognitionResult with transcript and confidence

        Raises:
            STTError: Base exception for STT errors
            STTTimeoutError: When request times out after all retries
            STTConnectionError: When unable to connect to service after all retries
            STTServiceError: When service returns a non-retryable error
            ValueError: When input validation fails
        """
        # Input validation
        if not audio_data:
            raise ValueError("audio_data cannot be empty")

        if sample_rate <= 0:
            raise ValueError(f"sample_rate must be positive, got {sample_rate}")

        if timeout is not None and timeout <= 0:
            raise ValueError(f"timeout must be positive, got {timeout}")

        # Build request
        cfg = (config or RecognitionConfig()).to_proto()
        request = asr_pb2.RecognitionRequest(
            audio_data=audio_data,
            sample_rate=sample_rate,
            encoding=encoding,
            config=cfg,
        )

        # Retry loop with exponential backoff
        last_exception = None
        backoff = self.initial_backoff

        for attempt in range(self.max_retries + 1):
            try:
                # Send request to STT service
                if attempt == 0:
                    logger.debug(
                        f"Sending STT recognize request: {len(audio_data)} bytes, "
                        f"sample_rate={sample_rate}, encoding={encoding}, timeout={timeout}"
                    )
                else:
                    logger.info(
                        f"Retrying STT recognize request (attempt {attempt + 1}/{self.max_retries + 1})"
                    )

                response = await self._stub.Recognize(request, timeout=timeout)

                # Extract transcribed text from response
                if response.results and len(response.results) > 0:
                    r = response.results[0]
                    transcript = r.transcript if r.transcript else ""
                    confidence = r.confidence if r.confidence >= 0 else 0.0
                    detected_language = getattr(r, "detected_language", None) or None

                    if attempt > 0:
                        logger.info(
                            f"STT recognition successful after {attempt} retries: "
                            f"transcript='{transcript[:50]}...', confidence={confidence:.2f}"
                        )
                    else:
                        logger.debug(
                            f"STT recognition successful: transcript='{transcript[:50]}...', "
                            f"confidence={confidence:.2f}"
                        )

                    result = RecognitionResult(
                        transcript=transcript,
                        confidence=confidence,
                        is_final=True,
                        detected_language=detected_language,
                    )
                    result.start_time_us = getattr(r, "start_time_us", 0)
                    result.end_time_us = getattr(r, "end_time_us", 0)
                    result.words = list(getattr(r, "words", []))
                    return result
                else:
                    # Empty response - no transcription available
                    logger.warning("STT service returned empty results")
                    return RecognitionResult(
                        transcript="",
                        confidence=0.0,
                        is_final=True,
                        detected_language=None,
                    )

            except grpc.RpcError as e:
                # Handle gRPC errors
                error_code = e.code()
                error_details = e.details()

                last_exception = e

                # Check if error is retryable
                if self._is_retryable_error(error_code) and attempt < self.max_retries:
                    logger.warning(
                        f"STT transient error (attempt {attempt + 1}/{self.max_retries + 1}): "
                        f"{error_code} - {error_details}. Retrying in {backoff:.2f}s..."
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * self.backoff_multiplier, self.max_backoff)
                    continue

                # Non-retryable error or max retries exceeded
                logger.error(
                    f"STT gRPC error: {error_code} - {error_details}", exc_info=True
                )

                # Map gRPC error codes to custom exceptions
                if error_code == grpc.StatusCode.DEADLINE_EXCEEDED:
                    raise STTTimeoutError(
                        f"STT request timed out after {timeout}s (attempt {attempt + 1}): {error_details}"
                    ) from e
                elif error_code in (
                    grpc.StatusCode.UNAVAILABLE,
                    grpc.StatusCode.CANCELLED,
                ):
                    raise STTConnectionError(
                        f"Unable to connect to STT service ({error_code}) after {attempt + 1} attempts: {error_details}"
                    ) from e
                elif error_code == grpc.StatusCode.INVALID_ARGUMENT:
                    raise ValueError(
                        f"Invalid request to STT service: {error_details}"
                    ) from e
                else:
                    raise STTServiceError(
                        f"STT service error ({error_code}): {error_details}"
                    ) from e

            except Exception as e:
                # Handle unexpected errors (not retryable)
                logger.error(f"Unexpected error in STT recognize: {e}", exc_info=True)
                raise STTError(
                    f"Unexpected error during STT recognition: {str(e)}"
                ) from e

        # If we exhausted all retries, raise the last exception
        if last_exception:
            error_code = last_exception.code()
            error_details = last_exception.details()
            if error_code == grpc.StatusCode.DEADLINE_EXCEEDED:
                raise STTTimeoutError(
                    f"STT request timed out after {self.max_retries + 1} attempts: {error_details}"
                ) from last_exception
            else:
                raise STTConnectionError(
                    f"Unable to connect to STT service after {self.max_retries + 1} attempts ({error_code}): {error_details}"
                ) from last_exception

        # Fallback (should not reach here)
        raise STTError("STT recognition failed unexpectedly")

    async def recognize_stream(
        self,
        audio_chunks,
        sample_rate: int = 16000,
        encoding: str = "pcm",
        config: Optional[RecognitionConfig] = None,
        timeout: Optional[float] = 30.0,
    ):
        """
        Stream audio chunks to STT RecognizeStream endpoint and yield transcription results.

        This method provides real-time transcription feedback as audio is processed.
        Results are yielded as they become available, with interim results for long audio.

        Args:
            audio_chunks: Async generator or iterable of audio data bytes
            sample_rate: Audio sample rate (default: 16000 Hz)
            encoding: Audio encoding format (default: "pcm")
            config: Optional recognition configuration
            timeout: Request timeout in seconds (default: 30.0)

        Yields:
            RecognitionResult objects with transcript, is_final flag, and confidence

        Raises:
            STTError: Base exception for STT errors
            STTTimeoutError: When request times out
            STTConnectionError: When unable to connect to service
            STTServiceError: When service returns an error
            ValueError: When input validation fails
        """
        # Input validation
        if sample_rate <= 0:
            raise ValueError(f"sample_rate must be positive, got {sample_rate}")

        if timeout is not None and timeout <= 0:
            raise ValueError(f"timeout must be positive, got {timeout}")

        # Note: RecognizeStream doesn't support config in chunks yet
        # Config will be ignored for streaming (language detection happens automatically)

        # Create async generator for audio chunks
        async def audio_chunk_generator():
            timestamp_us = 0
            chunk_duration_us = int(
                (1.0 / sample_rate) * 1_000_000
            )  # Duration per sample in microseconds

            async for chunk_data in audio_chunks:
                if not chunk_data:
                    continue

                chunk = asr_pb2.AudioChunk(
                    audio_data=chunk_data,
                    sample_rate=sample_rate,
                    channels=1,
                    encoding=encoding,
                    timestamp_us=timestamp_us,
                )
                timestamp_us += (
                    len(chunk_data) // 2 * chunk_duration_us
                )  # Approximate timestamp
                yield chunk

        try:
            logger.debug(
                f"Starting STT streaming recognition: sample_rate={sample_rate}, "
                f"encoding={encoding}, timeout={timeout}"
            )

            # Stream audio chunks and receive results
            async for result_proto in self._stub.RecognizeStream(
                audio_chunk_generator(), timeout=timeout
            ):
                # Convert proto result to RecognitionResult
                result = RecognitionResult(
                    transcript=result_proto.transcript
                    if result_proto.transcript
                    else "",
                    confidence=result_proto.confidence
                    if result_proto.confidence >= 0
                    else 0.0,
                    is_final=result_proto.is_final,
                    detected_language=getattr(result_proto, "detected_language", None)
                    or None,
                )
                # Add additional fields from proto
                result.start_time_us = result_proto.start_time_us
                result.end_time_us = result_proto.end_time_us
                result.words = result_proto.words

                logger.debug(
                    f"STT streaming result: transcript='{result.transcript[:50]}...', "
                    f"is_final={result.is_final}, confidence={result.confidence:.2f}"
                )

                yield result

        except grpc.RpcError as e:
            # Handle gRPC errors
            error_code = e.code()
            error_details = e.details()

            logger.error(
                f"STT streaming gRPC error: {error_code} - {error_details}",
                exc_info=True,
            )

            # Map gRPC error codes to custom exceptions
            if error_code == grpc.StatusCode.DEADLINE_EXCEEDED:
                raise STTTimeoutError(
                    f"STT streaming request timed out after {timeout}s: {error_details}"
                ) from e
            elif error_code in (
                grpc.StatusCode.UNAVAILABLE,
                grpc.StatusCode.CANCELLED,
            ):
                raise STTConnectionError(
                    f"Unable to connect to STT service ({error_code}): {error_details}"
                ) from e
            elif error_code == grpc.StatusCode.INVALID_ARGUMENT:
                raise ValueError(
                    f"Invalid request to STT service: {error_details}"
                ) from e
            else:
                raise STTServiceError(
                    f"STT service error ({error_code}): {error_details}"
                ) from e

        except Exception as e:
            # Handle unexpected errors
            logger.error(
                f"Unexpected error in STT recognize_stream: {e}", exc_info=True
            )
            raise STTError(f"Unexpected error during STT streaming: {str(e)}") from e
