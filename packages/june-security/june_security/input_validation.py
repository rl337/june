"""
Input Validation Module - Comprehensive input validation for all services.

This module provides input validation functions that integrate with june-security
to prevent injection attacks, validate file uploads, and sanitize user inputs.
"""
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Try to import python-magic, but make it optional
try:
    import magic

    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False
    magic = None

from .validator import SecurityValidator, ValidationResult

logger = logging.getLogger(__name__)


class InputValidationError(Exception):
    """Exception raised when input validation fails."""

    pass


class InputValidator:
    """
    Comprehensive input validator for all service types.

    Features:
    - String sanitization and validation
    - File upload validation (size, type, content)
    - SQL injection prevention helpers
    - XSS prevention
    - Schema validation
    - Business rule validation
    """

    # Maximum input lengths
    MAX_STRING_LENGTH = 100000  # 100KB
    MAX_FILENAME_LENGTH = 255
    MAX_QUERY_PARAM_LENGTH = 2048
    MAX_HEADER_LENGTH = 8192

    # Allowed file extensions for audio uploads
    ALLOWED_AUDIO_EXTENSIONS = {
        ".wav",
        ".mp3",
        ".ogg",
        ".flac",
        ".m4a",
        ".webm",
        ".opus",
    }
    ALLOWED_AUDIO_MIME_TYPES = {
        "audio/wav",
        "audio/wave",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/ogg",
        "audio/vorbis",
        "audio/opus",
        "audio/flac",
        "audio/mp4",
        "audio/m4a",
        "audio/webm",
    }

    # Maximum file sizes (in bytes)
    MAX_AUDIO_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    MAX_IMAGE_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_GENERIC_FILE_SIZE = 100 * 1024 * 1024  # 100MB

    # SQL injection patterns
    SQL_INJECTION_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE|UNION|SCRIPT)\b)",
        r"(--|#|\/\*|\*\/|;|\||&)",
        r"(\b(OR|AND)\s+\d+\s*=\s*\d+)",
        r"('|(\\')|(;)|(\\)|(\%27)|(\%00))",
        r"(\b(CHAR|ASCII|SUBSTRING|CAST|CONVERT)\s*\()",
    ]

    # XSS patterns
    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",  # onclick=, onerror=, etc.
        r"<iframe[^>]*>",
        r"<object[^>]*>",
        r"<embed[^>]*>",
        r"<link[^>]*>",
        r"<style[^>]*>",
        r"expression\s*\(",
        r"vbscript:",
    ]

    # Command injection patterns
    COMMAND_INJECTION_PATTERNS = [
        r"[;&|`$(){}[\]<>]",
        r"\b(cat|ls|pwd|whoami|id|uname|ps|kill|rm|mv|cp)\s+",
        r"\$\{.*\}",
        r"`.*`",
        r"\$\(.*\)",
    ]

    def __init__(self, security_validator: Optional[SecurityValidator] = None):
        """
        Initialize input validator.

        Args:
            security_validator: Optional SecurityValidator instance from june-security
        """
        self.security_validator = security_validator

        # Compile regex patterns for performance
        self.sql_injection_regex = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.SQL_INJECTION_PATTERNS
        ]
        self.xss_regex = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.XSS_PATTERNS
        ]
        self.command_injection_regex = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.COMMAND_INJECTION_PATTERNS
        ]

    def validate_string(
        self,
        value: Any,
        field_name: str = "input",
        max_length: Optional[int] = None,
        allow_empty: bool = False,
        sanitize: bool = True,
    ) -> str:
        """
        Validate and sanitize a string input.

        Args:
            value: Input value to validate
            field_name: Name of the field (for error messages)
            max_length: Maximum allowed length (default: MAX_STRING_LENGTH)
            allow_empty: Whether empty strings are allowed
            sanitize: Whether to sanitize the input using june-security

        Returns:
            Validated and sanitized string

        Raises:
            InputValidationError: If validation fails
        """
        if value is None:
            if allow_empty:
                return ""
            raise InputValidationError(f"{field_name} cannot be None")

        # Convert to string
        if not isinstance(value, str):
            value = str(value)

        # Check if empty
        if not value.strip() and not allow_empty:
            raise InputValidationError(f"{field_name} cannot be empty")

        # Sanitize using june-security if available
        if sanitize and self.security_validator:
            value = self.security_validator.sanitize_input(value)

        # Check length
        max_len = max_length or self.MAX_STRING_LENGTH
        if len(value) > max_len:
            raise InputValidationError(
                f"{field_name} exceeds maximum length of {max_len} characters"
            )

        return value

    def validate_integer(
        self,
        value: Any,
        field_name: str = "input",
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
    ) -> int:
        """
        Validate an integer input.

        Args:
            value: Input value to validate
            field_name: Name of the field (for error messages)
            min_value: Minimum allowed value
            max_value: Maximum allowed value

        Returns:
            Validated integer

        Raises:
            InputValidationError: If validation fails
        """
        try:
            int_value = int(value)
        except (ValueError, TypeError):
            raise InputValidationError(f"{field_name} must be a valid integer")

        if min_value is not None and int_value < min_value:
            raise InputValidationError(f"{field_name} must be at least {min_value}")

        if max_value is not None and int_value > max_value:
            raise InputValidationError(f"{field_name} must be at most {max_value}")

        return int_value

    def validate_float(
        self,
        value: Any,
        field_name: str = "input",
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
    ) -> float:
        """
        Validate a float input.

        Args:
            value: Input value to validate
            field_name: Name of the field (for error messages)
            min_value: Minimum allowed value
            max_value: Maximum allowed value

        Returns:
            Validated float

        Raises:
            InputValidationError: If validation fails
        """
        try:
            float_value = float(value)
        except (ValueError, TypeError):
            raise InputValidationError(f"{field_name} must be a valid number")

        if min_value is not None and float_value < min_value:
            raise InputValidationError(f"{field_name} must be at least {min_value}")

        if max_value is not None and float_value > max_value:
            raise InputValidationError(f"{field_name} must be at most {max_value}")

        return float_value

    def validate_enum(
        self,
        value: Any,
        allowed_values: List[str],
        field_name: str = "input",
        case_sensitive: bool = False,
    ) -> str:
        """
        Validate that a value is in a list of allowed values.

        Args:
            value: Input value to validate
            allowed_values: List of allowed values
            field_name: Name of the field (for error messages)
            case_sensitive: Whether comparison should be case-sensitive

        Returns:
            Validated value

        Raises:
            InputValidationError: If validation fails
        """
        value_str = str(value)

        if not case_sensitive:
            value_str = value_str.lower()
            allowed_values = [v.lower() for v in allowed_values]

        if value_str not in allowed_values:
            raise InputValidationError(
                f"{field_name} must be one of: {', '.join(allowed_values)}"
            )

        return str(value)

    def validate_sql_safe(self, value: str, field_name: str = "input") -> str:
        """
        Validate that a string is safe from SQL injection.

        Note: This is a helper for validation. Always use parameterized queries
        in actual database operations.

        Args:
            value: Input value to validate
            field_name: Name of the field (for error messages)

        Returns:
            Validated string

        Raises:
            InputValidationError: If SQL injection pattern detected
        """
        value = self.validate_string(value, field_name)

        # Check for SQL injection patterns
        for pattern in self.sql_injection_regex:
            if pattern.search(value):
                logger.warning(
                    f"SQL injection attempt detected in {field_name}: {value[:100]}"
                )
                raise InputValidationError(
                    f"{field_name} contains potentially dangerous SQL patterns"
                )

        return value

    def validate_xss_safe(self, value: str, field_name: str = "input") -> str:
        """
        Validate that a string is safe from XSS attacks.

        Args:
            value: Input value to validate
            field_name: Name of the field (for error messages)

        Returns:
            Validated string

        Raises:
            InputValidationError: If XSS pattern detected
        """
        value = self.validate_string(value, field_name)

        # Check for XSS patterns
        for pattern in self.xss_regex:
            if pattern.search(value):
                logger.warning(f"XSS attempt detected in {field_name}: {value[:100]}")
                raise InputValidationError(
                    f"{field_name} contains potentially dangerous XSS patterns"
                )

        return value

    def validate_command_safe(self, value: str, field_name: str = "input") -> str:
        """
        Validate that a string is safe from command injection.

        Args:
            value: Input value to validate
            field_name: Name of the field (for error messages)

        Returns:
            Validated string

        Raises:
            InputValidationError: If command injection pattern detected
        """
        value = self.validate_string(value, field_name)

        # Check for command injection patterns
        for pattern in self.command_injection_regex:
            if pattern.search(value):
                logger.warning(
                    f"Command injection attempt detected in {field_name}: {value[:100]}"
                )
                raise InputValidationError(
                    f"{field_name} contains potentially dangerous command patterns"
                )

        return value

    def validate_file_upload(
        self,
        file_content: bytes,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        max_size: Optional[int] = None,
        allowed_extensions: Optional[List[str]] = None,
        allowed_mime_types: Optional[List[str]] = None,
        validate_content: bool = True,
    ) -> Tuple[bytes, str, str]:
        """
        Validate a file upload.

        Args:
            file_content: File content as bytes
            filename: Original filename (optional)
            content_type: Content type/MIME type (optional)
            max_size: Maximum file size in bytes (default: MAX_GENERIC_FILE_SIZE)
            allowed_extensions: List of allowed file extensions (e.g., ['.wav', '.mp3'])
            allowed_mime_types: List of allowed MIME types (e.g., ['audio/wav', 'audio/mp3'])
            validate_content: Whether to validate file content using magic numbers

        Returns:
            Tuple of (validated_content, validated_filename, validated_mime_type)

        Raises:
            InputValidationError: If validation fails
        """
        # Validate file size
        max_file_size = max_size or self.MAX_GENERIC_FILE_SIZE
        if len(file_content) > max_file_size:
            raise InputValidationError(
                f"File size ({len(file_content)} bytes) exceeds maximum allowed size ({max_file_size} bytes)"
            )

        if len(file_content) == 0:
            raise InputValidationError("File is empty")

        # Validate filename
        validated_filename = filename or "upload"
        if len(validated_filename) > self.MAX_FILENAME_LENGTH:
            raise InputValidationError(
                f"Filename exceeds maximum length of {self.MAX_FILENAME_LENGTH} characters"
            )

        # Check for directory traversal in filename
        if (
            ".." in validated_filename
            or "/" in validated_filename
            or "\\" in validated_filename
        ):
            raise InputValidationError(
                "Filename contains invalid characters (directory traversal attempt)"
            )

        # Get file extension
        file_ext = Path(validated_filename).suffix.lower()

        # Detect MIME type from content if not provided
        detected_mime_type = None
        if validate_content:
            if MAGIC_AVAILABLE and magic:
                try:
                    detected_mime_type = magic.from_buffer(file_content, mime=True)
                except Exception:
                    # Fallback to mimetypes if magic fails
                    detected_mime_type, _ = mimetypes.guess_type(validated_filename)
            else:
                # Fallback to mimetypes if python-magic is not available
                detected_mime_type, _ = mimetypes.guess_type(validated_filename)

        validated_mime_type = (
            content_type or detected_mime_type or "application/octet-stream"
        )

        # Validate extension if specified
        if allowed_extensions:
            if file_ext not in allowed_extensions:
                raise InputValidationError(
                    f"File extension '{file_ext}' is not allowed. Allowed extensions: {', '.join(allowed_extensions)}"
                )

        # Validate MIME type if specified
        if allowed_mime_types:
            if validated_mime_type not in allowed_mime_types:
                raise InputValidationError(
                    f"MIME type '{validated_mime_type}' is not allowed. Allowed types: {', '.join(allowed_mime_types)}"
                )

        return file_content, validated_filename, validated_mime_type

    def validate_audio_file(
        self,
        file_content: bytes,
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> Tuple[bytes, str, str]:
        """
        Validate an audio file upload.

        Args:
            file_content: File content as bytes
            filename: Original filename (optional)
            content_type: Content type/MIME type (optional)

        Returns:
            Tuple of (validated_content, validated_filename, validated_mime_type)

        Raises:
            InputValidationError: If validation fails
        """
        return self.validate_file_upload(
            file_content=file_content,
            filename=filename,
            content_type=content_type,
            max_size=self.MAX_AUDIO_FILE_SIZE,
            allowed_extensions=list(self.ALLOWED_AUDIO_EXTENSIONS),
            allowed_mime_types=list(self.ALLOWED_AUDIO_MIME_TYPES),
            validate_content=True,
        )

    def validate_query_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and sanitize query parameters.

        Args:
            params: Dictionary of query parameters

        Returns:
            Validated and sanitized parameters

        Raises:
            InputValidationError: If validation fails
        """
        validated = {}

        for key, value in params.items():
            # Validate key
            validated_key = self.validate_string(
                key,
                field_name=f"query parameter key '{key}'",
                max_length=self.MAX_QUERY_PARAM_LENGTH,
                sanitize=True,
            )

            # Validate value
            if isinstance(value, str):
                validated_value = self.validate_string(
                    value,
                    field_name=f"query parameter '{key}'",
                    max_length=self.MAX_QUERY_PARAM_LENGTH,
                    sanitize=True,
                )
            elif isinstance(value, (int, float)):
                validated_value = value
            elif isinstance(value, list):
                validated_value = [
                    self.validate_string(
                        str(v),
                        field_name=f"query parameter '{key}[{i}]'",
                        max_length=self.MAX_QUERY_PARAM_LENGTH,
                        sanitize=True,
                    )
                    for i, v in enumerate(value)
                ]
            else:
                validated_value = value

            validated[validated_key] = validated_value

        return validated

    def validate_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """
        Validate and sanitize HTTP headers.

        Args:
            headers: Dictionary of HTTP headers

        Returns:
            Validated and sanitized headers

        Raises:
            InputValidationError: If validation fails
        """
        validated = {}

        for key, value in headers.items():
            # Validate key
            validated_key = self.validate_string(
                key,
                field_name=f"header key '{key}'",
                max_length=self.MAX_HEADER_LENGTH,
                sanitize=True,
            )

            # Validate value
            validated_value = self.validate_string(
                value,
                field_name=f"header '{key}'",
                max_length=self.MAX_HEADER_LENGTH,
                sanitize=True,
            )

            validated[validated_key] = validated_value

        return validated


# Global instance (can be initialized with SecurityValidator)
_global_validator: Optional[InputValidator] = None


def get_input_validator(
    security_validator: Optional[SecurityValidator] = None,
) -> InputValidator:
    """
    Get or create the global input validator instance.

    Args:
        security_validator: Optional SecurityValidator instance

    Returns:
        InputValidator instance
    """
    global _global_validator

    if _global_validator is None:
        _global_validator = InputValidator(security_validator=security_validator)
    elif (
        security_validator is not None and _global_validator.security_validator is None
    ):
        _global_validator.security_validator = security_validator

    return _global_validator


def set_input_validator(validator: InputValidator) -> None:
    """
    Set the global input validator instance.

    Args:
        validator: InputValidator instance
    """
    global _global_validator
    _global_validator = validator
