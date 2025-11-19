import grpc
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from june_grpc_api import asr, tts, llm
from june_grpc_api.generated import asr_pb2


def test_asr_shim_constructs():
    ch = grpc.insecure_channel("localhost:9")  # blackhole port; just construct stub
    client = asr.SpeechToTextClient(ch)
    assert client is not None


def test_tts_shim_constructs():
    ch = grpc.insecure_channel("localhost:9")
    client = tts.TextToSpeechClient(ch)
    assert client is not None


def test_llm_shim_constructs():
    ch = grpc.insecure_channel("localhost:9")
    client = llm.LLMClient(ch)
    assert client is not None


# STT Client Error Handling Tests


@pytest.mark.asyncio
async def test_stt_recognize_success():
    """Test successful STT recognition."""
    channel = grpc.insecure_channel("localhost:9")
    client = asr.SpeechToTextClient(channel)

    # Mock successful response
    mock_response = asr_pb2.RecognitionResponse()
    result = asr_pb2.RecognitionResult(transcript="Hello world", confidence=0.95)
    mock_response.results.append(result)

    with patch.object(
        client._stub, "Recognize", new_callable=AsyncMock
    ) as mock_recognize:
        mock_recognize.return_value = mock_response

        result = await client.recognize(b"fake_audio_data", sample_rate=16000)

        assert result.transcript == "Hello world"
        assert result.confidence == 0.95
        mock_recognize.assert_called_once()


@pytest.mark.asyncio
async def test_stt_recognize_empty_audio():
    """Test that empty audio data raises ValueError."""
    channel = grpc.insecure_channel("localhost:9")
    client = asr.SpeechToTextClient(channel)

    with pytest.raises(ValueError, match="audio_data cannot be empty"):
        await client.recognize(b"", sample_rate=16000)


@pytest.mark.asyncio
async def test_stt_recognize_invalid_sample_rate():
    """Test that invalid sample_rate raises ValueError."""
    channel = grpc.insecure_channel("localhost:9")
    client = asr.SpeechToTextClient(channel)

    with pytest.raises(ValueError, match="sample_rate must be positive"):
        await client.recognize(b"fake_audio", sample_rate=-1)

    with pytest.raises(ValueError, match="sample_rate must be positive"):
        await client.recognize(b"fake_audio", sample_rate=0)


@pytest.mark.asyncio
async def test_stt_recognize_invalid_timeout():
    """Test that invalid timeout raises ValueError."""
    channel = grpc.insecure_channel("localhost:9")
    client = asr.SpeechToTextClient(channel)

    with pytest.raises(ValueError, match="timeout must be positive"):
        await client.recognize(b"fake_audio", timeout=-1)

    with pytest.raises(ValueError, match="timeout must be positive"):
        await client.recognize(b"fake_audio", timeout=0)


@pytest.mark.asyncio
async def test_stt_recognize_timeout_error():
    """Test that timeout errors raise STTTimeoutError after retries."""
    channel = grpc.insecure_channel("localhost:9")
    # Set max_retries to 0 to test immediate failure
    client = asr.SpeechToTextClient(channel, max_retries=0)

    # Mock timeout error
    mock_error = grpc.RpcError()
    mock_error.code = MagicMock(return_value=grpc.StatusCode.DEADLINE_EXCEEDED)
    mock_error.details = MagicMock(return_value="Request timed out")

    with patch.object(
        client._stub, "Recognize", new_callable=AsyncMock
    ) as mock_recognize:
        mock_recognize.side_effect = mock_error

        with pytest.raises(asr.STTTimeoutError, match="timed out"):
            await client.recognize(b"fake_audio", timeout=5.0)

        # Should only be called once (no retries with max_retries=0)
        assert mock_recognize.call_count == 1


@pytest.mark.asyncio
async def test_stt_recognize_connection_error():
    """Test that connection errors raise STTConnectionError after retries."""
    channel = grpc.insecure_channel("localhost:9")
    # Set max_retries to 0 to test immediate failure
    client = asr.SpeechToTextClient(channel, max_retries=0)

    # Mock unavailable error
    mock_error = grpc.RpcError()
    mock_error.code = MagicMock(return_value=grpc.StatusCode.UNAVAILABLE)
    mock_error.details = MagicMock(return_value="Service unavailable")

    with patch.object(
        client._stub, "Recognize", new_callable=AsyncMock
    ) as mock_recognize:
        mock_recognize.side_effect = mock_error

        with pytest.raises(asr.STTConnectionError, match="Unable to connect"):
            await client.recognize(b"fake_audio")

        # Should only be called once (no retries with max_retries=0)
        assert mock_recognize.call_count == 1


@pytest.mark.asyncio
async def test_stt_recognize_service_error():
    """Test that service errors raise STTServiceError."""
    channel = grpc.insecure_channel("localhost:9")
    client = asr.SpeechToTextClient(channel)

    # Mock internal error
    mock_error = grpc.RpcError()
    mock_error.code = MagicMock(return_value=grpc.StatusCode.INTERNAL)
    mock_error.details = MagicMock(return_value="Internal server error")

    with patch.object(
        client._stub, "Recognize", new_callable=AsyncMock
    ) as mock_recognize:
        mock_recognize.side_effect = mock_error

        with pytest.raises(asr.STTServiceError, match="STT service error"):
            await client.recognize(b"fake_audio")


@pytest.mark.asyncio
async def test_stt_recognize_empty_response():
    """Test handling of empty response from STT service."""
    channel = grpc.insecure_channel("localhost:9")
    client = asr.SpeechToTextClient(channel)

    # Mock empty response
    mock_response = asr_pb2.RecognitionResponse()

    with patch.object(
        client._stub, "Recognize", new_callable=AsyncMock
    ) as mock_recognize:
        mock_recognize.return_value = mock_response

        result = await client.recognize(b"fake_audio_data")

        assert result.transcript == ""
        assert result.confidence == 0.0


# Retry Logic Tests


@pytest.mark.asyncio
async def test_stt_retry_on_transient_error():
    """Test that transient errors trigger retries and succeed after retry."""
    channel = grpc.insecure_channel("localhost:9")
    client = asr.SpeechToTextClient(channel, max_retries=3, initial_backoff=0.1)

    # Mock response: first call fails, second succeeds
    mock_error = grpc.RpcError()
    mock_error.code = MagicMock(return_value=grpc.StatusCode.UNAVAILABLE)
    mock_error.details = MagicMock(return_value="Service temporarily unavailable")

    mock_response = asr_pb2.RecognitionResponse()
    result = asr_pb2.RecognitionResult(transcript="Hello world", confidence=0.95)
    mock_response.results.append(result)

    with patch.object(
        client._stub, "Recognize", new_callable=AsyncMock
    ) as mock_recognize, patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_recognize.side_effect = [mock_error, mock_response]

        result = await client.recognize(b"fake_audio_data")

        assert result.transcript == "Hello world"
        assert result.confidence == 0.95
        assert mock_recognize.call_count == 2
        # Should have slept once (before retry)
        assert mock_sleep.call_count == 1
        # First sleep uses initial_backoff
        mock_sleep.assert_called_once_with(0.1)


@pytest.mark.asyncio
async def test_stt_retry_exponential_backoff():
    """Test that exponential backoff works correctly."""
    channel = grpc.insecure_channel("localhost:9")
    client = asr.SpeechToTextClient(
        channel,
        max_retries=3,
        initial_backoff=0.1,
        max_backoff=1.0,
        backoff_multiplier=2.0,
    )

    # Mock error that persists for multiple retries
    mock_error = grpc.RpcError()
    mock_error.code = MagicMock(return_value=grpc.StatusCode.UNAVAILABLE)
    mock_error.details = MagicMock(return_value="Service unavailable")

    with patch.object(
        client._stub, "Recognize", new_callable=AsyncMock
    ) as mock_recognize, patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_recognize.side_effect = mock_error

        with pytest.raises(asr.STTConnectionError):
            await client.recognize(b"fake_audio_data")

        # Should retry 3 times (max_retries=3 means 3 retries after initial attempt)
        assert mock_recognize.call_count == 4  # 1 initial + 3 retries
        assert mock_sleep.call_count == 3

        # Check exponential backoff progression
        # After attempt 0 fails: sleep(initial_backoff=0.1), then backoff = 0.1 * 2.0 = 0.2
        # After attempt 1 fails: sleep(backoff=0.2), then backoff = 0.2 * 2.0 = 0.4
        # After attempt 2 fails: sleep(backoff=0.4), then backoff = 0.4 * 2.0 = 0.8
        # (max_backoff is 1.0, but 0.8 < 1.0, so no capping needed)
        expected_sleeps = [0.1, 0.2, 0.4]
        actual_sleeps = [call[0][0] for call in mock_sleep.call_args_list]
        assert actual_sleeps == expected_sleeps


@pytest.mark.asyncio
async def test_stt_retry_max_backoff_limit():
    """Test that backoff is capped at max_backoff."""
    channel = grpc.insecure_channel("localhost:9")
    client = asr.SpeechToTextClient(
        channel,
        max_retries=3,
        initial_backoff=1.0,
        max_backoff=2.0,
        backoff_multiplier=2.0,
    )

    mock_error = grpc.RpcError()
    mock_error.code = MagicMock(return_value=grpc.StatusCode.UNAVAILABLE)
    mock_error.details = MagicMock(return_value="Service unavailable")

    with patch.object(
        client._stub, "Recognize", new_callable=AsyncMock
    ) as mock_recognize, patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_recognize.side_effect = mock_error

        with pytest.raises(asr.STTConnectionError):
            await client.recognize(b"fake_audio_data")

        # Check that backoff is capped at max_backoff
        # After attempt 0 fails: sleep(initial_backoff=1.0), then backoff = 1.0 * 2.0 = 2.0 (capped at max_backoff=2.0)
        # After attempt 1 fails: sleep(backoff=2.0), then backoff = 2.0 * 2.0 = 4.0 (capped at max_backoff=2.0)
        # After attempt 2 fails: sleep(backoff=2.0), then backoff = 2.0 * 2.0 = 4.0 (capped at max_backoff=2.0)
        expected_sleeps = [1.0, 2.0, 2.0]
        actual_sleeps = [call[0][0] for call in mock_sleep.call_args_list]
        assert actual_sleeps == expected_sleeps


@pytest.mark.asyncio
async def test_stt_no_retry_on_non_retryable_error():
    """Test that non-retryable errors don't trigger retries."""
    channel = grpc.insecure_channel("localhost:9")
    client = asr.SpeechToTextClient(channel, max_retries=3)

    # INVALID_ARGUMENT is not retryable
    mock_error = grpc.RpcError()
    mock_error.code = MagicMock(return_value=grpc.StatusCode.INVALID_ARGUMENT)
    mock_error.details = MagicMock(return_value="Invalid argument")

    with patch.object(
        client._stub, "Recognize", new_callable=AsyncMock
    ) as mock_recognize, patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_recognize.side_effect = mock_error

        with pytest.raises(ValueError, match="Invalid request"):
            await client.recognize(b"fake_audio_data")

        # Should only be called once (no retries for non-retryable errors)
        assert mock_recognize.call_count == 1
        # Should not sleep
        assert mock_sleep.call_count == 0


@pytest.mark.asyncio
async def test_stt_retry_success_after_multiple_failures():
    """Test that retry succeeds after multiple transient failures."""
    channel = grpc.insecure_channel("localhost:9")
    client = asr.SpeechToTextClient(channel, max_retries=3, initial_backoff=0.1)

    mock_error = grpc.RpcError()
    mock_error.code = MagicMock(return_value=grpc.StatusCode.DEADLINE_EXCEEDED)
    mock_error.details = MagicMock(return_value="Request timeout")

    mock_response = asr_pb2.RecognitionResponse()
    result = asr_pb2.RecognitionResult(transcript="Retry success", confidence=0.9)
    mock_response.results.append(result)

    with patch.object(
        client._stub, "Recognize", new_callable=AsyncMock
    ) as mock_recognize, patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        # Fail twice, then succeed
        mock_recognize.side_effect = [mock_error, mock_error, mock_response]

        result = await client.recognize(b"fake_audio_data")

        assert result.transcript == "Retry success"
        assert result.confidence == 0.9
        assert mock_recognize.call_count == 3
        assert mock_sleep.call_count == 2  # Sleep before each retry
