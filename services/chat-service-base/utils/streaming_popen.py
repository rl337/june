"""
Reusable streaming Popen implementation using PTY for real-time output streaming.

This module provides a generator-based interface for streaming subprocess output
with proper PTY allocation for immediate, unbuffered output capture.
"""
import os
import pty
import select
import termios
import tty
from typing import Iterator, Tuple, Optional, Dict


def streaming_popen_generator(
    command: list,
    env: Optional[Dict[str, str]] = None,
    chunk_size: int = 1024,
    read_timeout: float = 0.05
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
            sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)
            sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 0)
        
        os.execve(command[0], command, env)
    else:
        # Parent process - read from PTY
        buffer = b''
        process_done = False
        returncode = None
        old_settings = None
        
        try:
            # Set PTY to raw mode for immediate character-by-character reading
            old_settings = termios.tcgetattr(master_fd)
            tty.setraw(master_fd)
            
            while True:
                # Check if process is done
                try:
                    wait_result = os.waitpid(pid, os.WNOHANG)
                    if wait_result[0] == pid:
                        process_done = True
                        returncode = os.WEXITSTATUS(wait_result[1])
                except OSError:
                    pass
                
                # Read from PTY (non-blocking)
                ready, _, _ = select.select([master_fd], [], [], read_timeout)
                if ready:
                    try:
                        data = os.read(master_fd, chunk_size)
                        if data:
                            buffer += data
                            # Process complete lines immediately
                            while b'\n' in buffer:
                                line_bytes, buffer = buffer.split(b'\n', 1)
                                line = line_bytes.decode('utf-8', errors='replace').strip()
                                if line:
                                    yield (line, False)
                    except (OSError, EOFError):
                        if process_done:
                            break
                
                # If process is done and no more data, break
                if process_done:
                    # Process any remaining data in buffer
                    if buffer:
                        line = buffer.decode('utf-8', errors='replace').strip()
                        if line:
                            yield (line, True)
                    break
            
            # Restore PTY settings
            if old_settings is not None:
                termios.tcsetattr(master_fd, termios.TCSADRAIN, old_settings)
        finally:
            try:
                os.close(master_fd)
            except:
                pass

