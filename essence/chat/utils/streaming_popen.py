"""
Reusable streaming Popen implementation using PTY for real-time output streaming.

This module provides a generator-based interface for streaming subprocess output
with proper PTY allocation for immediate, unbuffered output capture.
"""
import logging
import os
import pty
import select
import termios
import tty
from typing import Dict, Iterator, Optional, Tuple

# Import tracing utilities
try:
    from essence.chat.utils.tracing import get_or_create_tracer

    _tracer = get_or_create_tracer(__name__)
except ImportError:
    _tracer = None

logger = logging.getLogger(__name__)


def streaming_popen_generator(
    command: list,
    env: Optional[Dict[str, str]] = None,
    chunk_size: int = 1024,
    read_timeout: float = 0.05,
) -> Iterator[Tuple[str, bool]]:
    """
    Create a streaming generator from a subprocess using PTY.

    Uses PTY (pseudo-terminal) for proper terminal emulation, which ensures:
    - Unbuffered output (immediate flushing)
    - Proper terminal behavior for commands that check isatty()
    - Real-time streaming of output as it's produced

    Args:
        command: Command and arguments to execute (e.g., ["/bin/bash", "script.sh", "arg1"])
        env: Environment variables (defaults to current env if None)
        chunk_size: Size of chunks to read from PTY (default: 1024 bytes)
        read_timeout: Timeout for select() calls in seconds (default: 0.05s for responsive reading)

    Yields:
        Tuples of (line, is_final) where:
        - line: A line of output (without newline, stripped)
        - is_final: True if process has finished and this is the last line, False otherwise

    Example:
        >>> for line, is_final in streaming_popen_generator(["/bin/echo", "hello"]):
        ...     print(f"Line: {line}, Final: {is_final}")
        Line: hello, Final: True
    """
    if env is None:
        env = os.environ.copy()

    # Start tracing span for streaming operation
    span = None
    start_time = None
    if _tracer:
        span = _tracer.start_span(
            "streaming_popen_generator",
            attributes={
                "command": " ".join(command),
                "chunk_size": chunk_size,
                "read_timeout": read_timeout,
            },
        )
        import time

        start_time = time.time()

    # Create PTY and fork
    pid, master_fd = pty.fork()

    if pid == 0:
        # Child process - execute command
        # Set unbuffered output for immediate flushing
        import sys

        try:
            sys.stdout.reconfigure(line_buffering=True)
            sys.stderr.reconfigure(line_buffering=True)
        except (AttributeError, ValueError):
            # Python < 3.7 or reconfigure not available, use unbuffered mode
            sys.stdout = os.fdopen(sys.stdout.fileno(), "w", 0)
            sys.stderr = os.fdopen(sys.stderr.fileno(), "w", 0)

        os.execve(command[0], command, env)
    else:
        # Parent process - read from PTY
        buffer = b""
        process_done = False
        returncode = None
        old_settings = None
        first_read = True
        first_data_time = None
        total_bytes_read = 0
        total_lines_yielded = 0

        try:
            if span:
                span.set_attribute("pid", pid)
            # Set PTY to raw mode for immediate character-by-character reading
            old_settings = termios.tcgetattr(master_fd)
            tty.setraw(master_fd)

            while True:
                # Update elapsed time for span
                if span:
                    import time

                    elapsed = time.time() - start_time

                # Check if process is done
                try:
                    wait_result = os.waitpid(pid, os.WNOHANG)
                    if wait_result[0] == pid:
                        process_done = True
                        returncode = os.WEXITSTATUS(wait_result[1])
                        if span:
                            span.add_event(
                                "process_completed",
                                attributes={
                                    "returncode": returncode,
                                    "elapsed_seconds": elapsed,
                                },
                            )
                except OSError:
                    pass

                # Read from PTY (non-blocking)
                ready, _, _ = select.select([master_fd], [], [], read_timeout)
                if ready:
                    try:
                        data = os.read(master_fd, chunk_size)
                        if data:
                            if first_read:
                                first_read = False
                                import time

                                first_data_time = time.time()
                                if span:
                                    span.add_event(
                                        "first_data_received",
                                        attributes={
                                            "first_bytes": data[:100].decode(
                                                "utf-8", errors="replace"
                                            ),
                                            "first_bytes_length": len(data),
                                        },
                                    )
                                logger.info(
                                    f"First data received: {len(data)} bytes, preview: {data[:100]}"
                                )

                            total_bytes_read += len(data)
                            buffer += data
                            # Process complete lines immediately
                            while b"\n" in buffer:
                                line_bytes, buffer = buffer.split(b"\n", 1)
                                line = line_bytes.decode(
                                    "utf-8", errors="replace"
                                ).strip()
                                if line:
                                    total_lines_yielded += 1
                                    if (
                                        span and total_lines_yielded <= 5
                                    ):  # Log first 5 lines
                                        span.add_event(
                                            "line_yielded",
                                            attributes={
                                                "line_number": total_lines_yielded,
                                                "line_preview": line[:100],
                                                "line_length": len(line),
                                            },
                                        )
                                    yield (line, False)
                    except (OSError, EOFError):
                        if process_done:
                            break

                # If process is done and no more data, break
                if process_done:
                    # Process any remaining data in buffer
                    if buffer:
                        line = buffer.decode("utf-8", errors="replace").strip()
                        if line:
                            total_lines_yielded += 1
                            if span:
                                span.add_event(
                                    "final_buffer_yielded",
                                    attributes={
                                        "buffer_length": len(line),
                                        "buffer_preview": line[:100],
                                    },
                                )
                            yield (line, True)

                    # Set span attributes with final stats
                    if span and start_time:
                        import time

                        total_elapsed = time.time() - start_time
                        span.set_attribute("total_bytes_read", total_bytes_read)
                        span.set_attribute("total_lines_yielded", total_lines_yielded)
                        span.set_attribute("returncode", returncode)
                        span.set_attribute("total_elapsed_seconds", total_elapsed)
                        if first_data_time:
                            time_to_first_data = first_data_time - start_time
                            span.set_attribute(
                                "time_to_first_data_ms", time_to_first_data * 1000
                            )
                    break

            # Restore PTY settings
            if old_settings is not None:
                termios.tcsetattr(master_fd, termios.TCSADRAIN, old_settings)
        finally:
            try:
                os.close(master_fd)
            except:
                pass
            if span:
                span.end()
