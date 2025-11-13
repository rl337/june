"""
Gateway Input Validation - Pydantic models and validation for Gateway service.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator, HttpUrl
from datetime import datetime
import re

from june_security import get_input_validator, InputValidationError


# Initialize input validator
input_validator = get_input_validator()


# Request Models
class LLMGenerateRequest(BaseModel):
    """Request model for LLM generation."""
    prompt: str = Field(..., min_length=1, max_length=100000, description="Text prompt for generation")
    
    @validator('prompt')
    def validate_prompt(cls, v):
        """Validate and sanitize prompt."""
        try:
            return input_validator.validate_string(
                v,
                field_name="prompt",
                max_length=100000,
                sanitize=True
            )
        except InputValidationError as e:
            raise ValueError(str(e))


class TTSSpeakRequest(BaseModel):
    """Request model for TTS synthesis."""
    text: str = Field(..., min_length=1, max_length=50000, description="Text to synthesize")
    language: str = Field(default="en", max_length=10, description="Language code (ISO 639-1)")
    voice_id: str = Field(default="default", max_length=100, description="Voice ID")
    
    @validator('text')
    def validate_text(cls, v):
        """Validate and sanitize text."""
        try:
            return input_validator.validate_string(
                v,
                field_name="text",
                max_length=50000,
                sanitize=True
            )
        except InputValidationError as e:
            raise ValueError(str(e))
    
    @validator('language')
    def validate_language(cls, v):
        """Validate language code."""
        if not re.match(r'^[a-z]{2}(-[A-Z]{2})?$', v):
            raise ValueError("Language must be a valid ISO 639-1 code (e.g., 'en', 'es', 'fr')")
        return v.lower()
    
    @validator('voice_id')
    def validate_voice_id(cls, v):
        """Validate voice ID."""
        try:
            return input_validator.validate_string(
                v,
                field_name="voice_id",
                max_length=100,
                sanitize=True
            )
        except InputValidationError as e:
            raise ValueError(str(e))


class LoginRequest(BaseModel):
    """Request model for user login."""
    username: Optional[str] = Field(None, max_length=255, description="Username (for username/password auth)")
    password: Optional[str] = Field(None, max_length=255, description="Password (for username/password auth)")
    user_id: Optional[str] = Field(None, max_length=255, description="User ID (for external auth)")
    
    @validator('username')
    def validate_username(cls, v):
        """Validate username."""
        if v is None:
            return v
        try:
            return input_validator.validate_string(
                v,
                field_name="username",
                max_length=255,
                sanitize=True
            )
        except InputValidationError as e:
            raise ValueError(str(e))
    
    @validator('user_id')
    def validate_user_id(cls, v):
        """Validate user_id."""
        if v is None:
            return v
        try:
            return input_validator.validate_string(
                v,
                field_name="user_id",
                max_length=255,
                sanitize=True
            )
        except InputValidationError as e:
            raise ValueError(str(e))


class RefreshTokenRequest(BaseModel):
    """Request model for token refresh."""
    refresh_token: str = Field(..., min_length=1, max_length=1000, description="Refresh token")
    
    @validator('refresh_token')
    def validate_refresh_token(cls, v):
        """Validate refresh token."""
        try:
            return input_validator.validate_string(
                v,
                field_name="refresh_token",
                max_length=1000,
                sanitize=True
            )
        except InputValidationError as e:
            raise ValueError(str(e))


class LogoutRequest(BaseModel):
    """Request model for logout."""
    refresh_token: str = Field(..., min_length=1, max_length=1000, description="Refresh token")
    
    @validator('refresh_token')
    def validate_refresh_token(cls, v):
        """Validate refresh token."""
        try:
            return input_validator.validate_string(
                v,
                field_name="refresh_token",
                max_length=1000,
                sanitize=True
            )
        except InputValidationError as e:
            raise ValueError(str(e))


class CreateUserRequest(BaseModel):
    """Request model for creating a user."""
    username: str = Field(..., min_length=1, max_length=255, description="Username")
    email: Optional[str] = Field(None, max_length=255, description="Email address")
    password: Optional[str] = Field(None, min_length=8, max_length=255, description="Password (min 8 characters)")
    role: str = Field(default="user", max_length=50, description="User role")
    status: str = Field(default="active", max_length=50, description="User status")
    
    @validator('username')
    def validate_username(cls, v):
        """Validate username."""
        try:
            validated = input_validator.validate_string(
                v,
                field_name="username",
                max_length=255,
                sanitize=True
            )
            # Additional validation: no special characters that could cause issues
            if not re.match(r'^[a-zA-Z0-9_-]+$', validated):
                raise ValueError("Username can only contain letters, numbers, underscores, and hyphens")
            return validated
        except InputValidationError as e:
            raise ValueError(str(e))
    
    @validator('email')
    def validate_email(cls, v):
        """Validate email address."""
        if v is None:
            return v
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError("Invalid email address format")
        return v.lower()
    
    @validator('role')
    def validate_role(cls, v):
        """Validate role."""
        allowed_roles = ['user', 'admin', 'moderator']
        return input_validator.validate_enum(v, allowed_roles, field_name="role", case_sensitive=False)
    
    @validator('status')
    def validate_status(cls, v):
        """Validate status."""
        allowed_statuses = ['active', 'blocked', 'inactive']
        return input_validator.validate_enum(v, allowed_statuses, field_name="status", case_sensitive=False)


class UpdateUserRequest(BaseModel):
    """Request model for updating a user."""
    username: Optional[str] = Field(None, max_length=255, description="Username")
    email: Optional[str] = Field(None, max_length=255, description="Email address")
    password: Optional[str] = Field(None, min_length=8, max_length=255, description="Password")
    role: Optional[str] = Field(None, max_length=50, description="User role")
    status: Optional[str] = Field(None, max_length=50, description="User status")
    
    @validator('username')
    def validate_username(cls, v):
        """Validate username."""
        if v is None:
            return v
        try:
            validated = input_validator.validate_string(
                v,
                field_name="username",
                max_length=255,
                sanitize=True
            )
            if not re.match(r'^[a-zA-Z0-9_-]+$', validated):
                raise ValueError("Username can only contain letters, numbers, underscores, and hyphens")
            return validated
        except InputValidationError as e:
            raise ValueError(str(e))
    
    @validator('email')
    def validate_email(cls, v):
        """Validate email address."""
        if v is None:
            return v
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError("Invalid email address format")
        return v.lower()
    
    @validator('role')
    def validate_role(cls, v):
        """Validate role."""
        if v is None:
            return v
        allowed_roles = ['user', 'admin', 'moderator']
        return input_validator.validate_enum(v, allowed_roles, field_name="role", case_sensitive=False)
    
    @validator('status')
    def validate_status(cls, v):
        """Validate status."""
        if v is None:
            return v
        allowed_statuses = ['active', 'blocked', 'inactive']
        return input_validator.validate_enum(v, allowed_statuses, field_name="status", case_sensitive=False)


class CreatePromptTemplateRequest(BaseModel):
    """Request model for creating a prompt template."""
    name: str = Field(..., min_length=1, max_length=255, description="Template name")
    template: str = Field(..., min_length=1, max_length=100000, description="Template content")
    user_id: Optional[str] = Field(None, max_length=255, description="User ID (for user-specific templates)")
    conversation_id: Optional[str] = Field(None, max_length=255, description="Conversation ID (for conversation-specific templates)")
    is_active: bool = Field(default=True, description="Whether template is active")
    
    @validator('name')
    def validate_name(cls, v):
        """Validate template name."""
        try:
            return input_validator.validate_string(
                v,
                field_name="name",
                max_length=255,
                sanitize=True
            )
        except InputValidationError as e:
            raise ValueError(str(e))
    
    @validator('template')
    def validate_template(cls, v):
        """Validate template content."""
        try:
            # Allow template content to be longer, but still sanitize
            return input_validator.validate_string(
                v,
                field_name="template",
                max_length=100000,
                sanitize=True
            )
        except InputValidationError as e:
            raise ValueError(str(e))


class UpdatePromptTemplateRequest(BaseModel):
    """Request model for updating a prompt template."""
    name: Optional[str] = Field(None, max_length=255, description="Template name")
    template: Optional[str] = Field(None, max_length=100000, description="Template content")
    is_active: Optional[bool] = Field(None, description="Whether template is active")
    
    @validator('name')
    def validate_name(cls, v):
        """Validate template name."""
        if v is None:
            return v
        try:
            return input_validator.validate_string(
                v,
                field_name="name",
                max_length=255,
                sanitize=True
            )
        except InputValidationError as e:
            raise ValueError(str(e))
    
    @validator('template')
    def validate_template(cls, v):
        """Validate template content."""
        if v is None:
            return v
        try:
            return input_validator.validate_string(
                v,
                field_name="template",
                max_length=100000,
                sanitize=True
            )
        except InputValidationError as e:
            raise ValueError(str(e))


class CreateABTestRequest(BaseModel):
    """Request model for creating an A/B test."""
    name: str = Field(..., min_length=1, max_length=255, description="Test name")
    description: Optional[str] = Field(None, max_length=1000, description="Test description")
    variants: List[Dict[str, Any]] = Field(..., min_items=2, description="Test variants")
    start_date: Optional[str] = Field(None, description="Start date (ISO format)")
    end_date: Optional[str] = Field(None, description="End date (ISO format)")
    
    @validator('name')
    def validate_name(cls, v):
        """Validate test name."""
        try:
            return input_validator.validate_string(
                v,
                field_name="name",
                max_length=255,
                sanitize=True
            )
        except InputValidationError as e:
            raise ValueError(str(e))
    
    @validator('description')
    def validate_description(cls, v):
        """Validate description."""
        if v is None:
            return v
        try:
            return input_validator.validate_string(
                v,
                field_name="description",
                max_length=1000,
                sanitize=True
            )
        except InputValidationError as e:
            raise ValueError(str(e))


class UpdateABTestRequest(BaseModel):
    """Request model for updating an A/B test."""
    name: Optional[str] = Field(None, max_length=255, description="Test name")
    description: Optional[str] = Field(None, max_length=1000, description="Test description")
    variants: Optional[List[Dict[str, Any]]] = Field(None, description="Test variants")
    start_date: Optional[str] = Field(None, description="Start date (ISO format)")
    end_date: Optional[str] = Field(None, description="End date (ISO format)")
    
    @validator('name')
    def validate_name(cls, v):
        """Validate test name."""
        if v is None:
            return v
        try:
            return input_validator.validate_string(
                v,
                field_name="name",
                max_length=255,
                sanitize=True
            )
        except InputValidationError as e:
            raise ValueError(str(e))
    
    @validator('description')
    def validate_description(cls, v):
        """Validate description."""
        if v is None:
            return v
        try:
            return input_validator.validate_string(
                v,
                field_name="description",
                max_length=1000,
                sanitize=True
            )
        except InputValidationError as e:
            raise ValueError(str(e))


class UpdateBotConfigRequest(BaseModel):
    """Request model for updating bot configuration."""
    config: Dict[str, Any] = Field(..., description="Bot configuration")
    
    @validator('config')
    def validate_config(cls, v):
        """Validate configuration."""
        if not isinstance(v, dict):
            raise ValueError("Config must be a dictionary")
        # Additional validation can be added here based on bot config schema
        return v


class UpdateSystemConfigRequest(BaseModel):
    """Request model for updating system configuration."""
    config: Dict[str, Any] = Field(..., description="System configuration")
    
    @validator('config')
    def validate_config(cls, v):
        """Validate configuration."""
        if not isinstance(v, dict):
            raise ValueError("Config must be a dictionary")
        # Additional validation can be added here based on system config schema
        return v


# Query Parameter Validation Helpers
def validate_query_string(value: Optional[str], field_name: str, max_length: int = 2048) -> Optional[str]:
    """Validate a query string parameter."""
    if value is None:
        return None
    try:
        return input_validator.validate_string(
            value,
            field_name=field_name,
            max_length=max_length,
            sanitize=True
        )
    except InputValidationError as e:
        raise ValueError(str(e))


def validate_user_id(user_id: str) -> str:
    """Validate a user ID."""
    try:
        return input_validator.validate_string(
            user_id,
            field_name="user_id",
            max_length=255,
            sanitize=True
        )
    except InputValidationError as e:
        raise ValueError(str(e))


def validate_conversation_id(conversation_id: str) -> str:
    """Validate a conversation ID."""
    try:
        return input_validator.validate_string(
            conversation_id,
            field_name="conversation_id",
            max_length=255,
            sanitize=True
        )
    except InputValidationError as e:
        raise ValueError(str(e))


def validate_date_string(date_str: Optional[str], field_name: str = "date") -> Optional[datetime]:
    """Validate and parse a date string."""
    if date_str is None:
        return None
    
    try:
        # Validate the string first
        validated_str = input_validator.validate_string(
            date_str,
            field_name=field_name,
            max_length=50,
            sanitize=True
        )
        
        # Try to parse ISO format
        try:
            return datetime.fromisoformat(validated_str.replace('Z', '+00:00'))
        except ValueError:
            # Try just date format
            return datetime.fromisoformat(f"{validated_str}T00:00:00")
    except InputValidationError as e:
        raise ValueError(f"Invalid {field_name} format: {str(e)}")


def validate_audio_file_upload(file_content: bytes, filename: Optional[str] = None, content_type: Optional[str] = None) -> Tuple[bytes, str, str]:
    """Validate an audio file upload."""
    try:
        return input_validator.validate_audio_file(
            file_content=file_content,
            filename=filename,
            content_type=content_type
        )
    except InputValidationError as e:
        raise ValueError(str(e))
