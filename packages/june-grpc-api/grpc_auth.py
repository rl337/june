"""
gRPC Authentication Interceptor for June services.

Provides authentication and authorization for gRPC services using JWT tokens
or service-to-service API keys.
"""
import logging
import os
from typing import Optional, Callable, Any
import grpc
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "")


class AuthenticationError(Exception):
    """Authentication error exception."""
    pass


def verify_jwt_token(token: str) -> dict:
    """
    Verify and decode a JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded token payload
        
    Raises:
        AuthenticationError: If token is invalid
    """
    if not JWT_SECRET:
        raise AuthenticationError("JWT_SECRET not configured")
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as e:
        raise AuthenticationError(f"Invalid token: {str(e)}")


def verify_service_api_key(api_key: str) -> bool:
    """
    Verify a service-to-service API key.
    
    Args:
        api_key: API key string
        
    Returns:
        True if API key is valid, False otherwise
    """
    if not SERVICE_API_KEY:
        logger.warning("SERVICE_API_KEY not configured")
        return False
    
    return api_key == SERVICE_API_KEY


def extract_token_from_metadata(metadata: tuple) -> Optional[str]:
    """
    Extract JWT token or API key from gRPC metadata.
    
    Args:
        metadata: gRPC metadata tuple
        
    Returns:
        Token string if found, None otherwise
    """
    for key, value in metadata:
        if key == "authorization":
            # Support both "Bearer <token>" and direct token
            if value.startswith("Bearer "):
                return value[7:]
            return value
        elif key == "x-api-key":
            return value
    
    return None


class AuthInterceptor(grpc.aio.ServerInterceptor):
    """
    gRPC authentication interceptor.
    
    Validates JWT tokens or service API keys from request metadata.
    """
    
    def __init__(self, require_auth: bool = True, allowed_services: list = None):
        """
        Initialize authentication interceptor.
        
        Args:
            require_auth: Whether authentication is required (default: True)
            allowed_services: List of service names allowed for service-to-service auth
        """
        self.require_auth = require_auth
        self.allowed_services = allowed_services or []
    
    async def intercept_service(
        self,
        continuation: Callable,
        handler_call_details: grpc.HandlerCallDetails
    ) -> grpc.RpcMethodHandler:
        """
        Intercept gRPC service calls to validate authentication.
        
        Args:
            continuation: Continuation function
            handler_call_details: Handler call details with metadata
            
        Returns:
            RPC method handler
            
        Raises:
            grpc.RpcError: If authentication fails
        """
        # Extract metadata
        metadata = handler_call_details.metadata or tuple()
        
        # Extract token
        token = extract_token_from_metadata(metadata)
        
        if not token:
            if self.require_auth:
                # No token provided and auth is required
                raise grpc.RpcError(
                    grpc.StatusCode.UNAUTHENTICATED,
                    "Authentication required"
                )
            # Auth not required, proceed
            return await continuation(handler_call_details)
        
        # Verify token
        try:
            # Try JWT token first
            try:
                payload = verify_jwt_token(token)
                
                # Check token type
                token_type = payload.get("type", "access")
                
                if token_type == "service":
                    # Service-to-service token
                    service_name = payload.get("service")
                    if self.allowed_services and service_name not in self.allowed_services:
                        raise grpc.RpcError(
                            grpc.StatusCode.PERMISSION_DENIED,
                            f"Service '{service_name}' not allowed"
                        )
                elif token_type == "access":
                    # User access token - check if user has required permissions
                    # This can be extended with permission checking
                    pass
                else:
                    raise grpc.RpcError(
                        grpc.StatusCode.UNAUTHENTICATED,
                        "Invalid token type"
                    )
                
                # Add user/service info to metadata for handler access
                new_metadata = list(metadata)
                new_metadata.append(("user_id", payload.get("sub", "")))
                new_metadata.append(("token_type", token_type))
                
                if token_type == "service":
                    new_metadata.append(("service_name", payload.get("service", "")))
                else:
                    roles = payload.get("roles", [])
                    if roles:
                        new_metadata.append(("roles", ",".join(roles)))
                
                # Create new handler call details with updated metadata
                new_handler_call_details = grpc.HandlerCallDetails(
                    method=handler_call_details.method,
                    invocation_metadata=tuple(new_metadata),
                    timeout=handler_call_details.timeout,
                    credentials=handler_call_details.credentials,
                    wait_for_ready=handler_call_details.wait_for_ready
                )
                
                return await continuation(new_handler_call_details)
                
            except AuthenticationError:
                # Not a JWT token, try service API key
                if verify_service_api_key(token):
                    # Valid service API key
                    new_metadata = list(metadata)
                    new_metadata.append(("token_type", "service"))
                    new_metadata.append(("service_name", "external"))
                    
                    new_handler_call_details = grpc.HandlerCallDetails(
                        method=handler_call_details.method,
                        invocation_metadata=tuple(new_metadata),
                        timeout=handler_call_details.timeout,
                        credentials=handler_call_details.credentials,
                        wait_for_ready=handler_call_details.wait_for_ready
                    )
                    
                    return await continuation(new_handler_call_details)
                else:
                    raise grpc.RpcError(
                        grpc.StatusCode.UNAUTHENTICATED,
                        "Invalid authentication token or API key"
                    )
        
        except grpc.RpcError:
            raise
        except Exception as e:
            logger.error(f"Authentication error: {e}", exc_info=True)
            raise grpc.RpcError(
                grpc.StatusCode.INTERNAL,
                "Authentication error"
            )


def create_auth_interceptor(require_auth: bool = True, allowed_services: list = None) -> AuthInterceptor:
    """
    Create an authentication interceptor.
    
    Args:
        require_auth: Whether authentication is required
        allowed_services: List of allowed service names
        
    Returns:
        AuthInterceptor instance
    """
    return AuthInterceptor(require_auth=require_auth, allowed_services=allowed_services)


def get_user_from_metadata(metadata: tuple) -> Optional[str]:
    """
    Extract user ID from gRPC metadata (set by auth interceptor).
    
    Args:
        metadata: gRPC metadata tuple
        
    Returns:
        User ID if found, None otherwise
    """
    for key, value in metadata:
        if key == "user_id":
            return value
    return None


def get_service_from_metadata(metadata: tuple) -> Optional[str]:
    """
    Extract service name from gRPC metadata (set by auth interceptor).
    
    Args:
        metadata: gRPC metadata tuple
        
    Returns:
        Service name if found, None otherwise
    """
    for key, value in metadata:
        if key == "service_name":
            return value
    return None


def is_service_request(metadata: tuple) -> bool:
    """
    Check if request is from a service (service-to-service).
    
    Args:
        metadata: gRPC metadata tuple
        
    Returns:
        True if request is from a service, False otherwise
    """
    for key, value in metadata:
        if key == "token_type" and value == "service":
            return True
    return False
