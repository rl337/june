"""
Tool executor with safety checks and audit logging.
"""

import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from june_agent_tools.tool import Tool, ToolResult
from june_agent_tools.registry import get_registry

logger = logging.getLogger(__name__)

# Import security components
try:
    from june_security.validator import SecurityValidator, OperationType, ValidationResult
    from june_security.audit import AuditLogger
    SECURITY_AVAILABLE = True
except ImportError:
    logger.warning("june-security not available - tools will run without security validation")
    SECURITY_AVAILABLE = False
    OperationType = Any  # Fallback type hint when june_security is not available


class ToolExecutor:
    """
    Executes tools with safety checks and audit logging.
    
    Features:
    - Parameter validation
    - Security validation (path checks, dangerous operations)
    - Audit logging of all operations
    - Error handling and reporting
    """
    
    def __init__(
        self,
        project_paths: Optional[List[str]] = None,
        enable_security: bool = True,
        enable_audit: bool = True
    ):
        """
        Initialize tool executor.
        
        Args:
            project_paths: List of allowed project root paths for path validation
            enable_security: Whether to enable security validation
            enable_audit: Whether to enable audit logging
        """
        self.project_paths = [Path(p).resolve() for p in (project_paths or [])]
        self.enable_security = enable_security and SECURITY_AVAILABLE
        self.enable_audit = enable_audit and SECURITY_AVAILABLE
        
        if self.enable_security:
            self.validator = SecurityValidator(
                allowed_project_paths=[str(p) for p in self.project_paths],
                block_dangerous_commands=True,
                require_path_validation=True,
                block_force_push_main=True
            )
        else:
            self.validator = None
        
        if self.enable_audit and SECURITY_AVAILABLE:
            try:
                self.audit_logger = AuditLogger()
            except Exception as e:
                logger.warning(f"Failed to initialize audit logger: {e}")
                self.enable_audit = False
                self.audit_logger = None
        else:
            self.audit_logger = None
            if self.enable_audit and not SECURITY_AVAILABLE:
                logger.warning("Audit logging requested but june-security not available")
                self.enable_audit = False
        
        logger.info(f"ToolExecutor initialized (security={self.enable_security}, audit={self.enable_audit})")
    
    def execute(
        self,
        tool_name: str,
        params: Dict[str, Any],
        agent_id: Optional[str] = None
    ) -> ToolResult:
        """
        Execute a tool with safety checks.
        
        Args:
            tool_name: Name of the tool to execute
            params: Tool parameters
            agent_id: Agent identifier for audit logging
            
        Returns:
            ToolResult with execution outcome
        """
        # Get tool from registry
        tool = get_registry().get(tool_name)
        if not tool:
            error_msg = f"Tool '{tool_name}' not found"
            logger.error(error_msg)
            if self.audit_logger:
                self.audit_logger.log_operation(
                    operation_type="tool_execution",
                    operation="tool_not_found",
                    agent_id=agent_id,
                    success=False,
                    error=error_msg,
                    metadata={"tool_name": tool_name}
                )
            return ToolResult(
                success=False,
                output="",
                error=error_msg
            )
        
        # Validate tool parameters
        if not tool.validate(params):
            error_msg = f"Invalid parameters for tool '{tool_name}'"
            logger.warning(f"{error_msg}: {params}")
            if self.audit_logger:
                self.audit_logger.log_operation(
                    operation_type="tool_execution",
                    operation=f"{tool_name}_validation_failed",
                    agent_id=agent_id,
                    success=False,
                    error=error_msg,
                    metadata={"tool_name": tool_name, "params": params}
                )
            return ToolResult(
                success=False,
                output="",
                error=error_msg
            )
        
        # Security validation
        if self.enable_security and self.validator:
            # Determine operation type from tool name and params
            operation_type = self._detect_operation_type(tool_name, params)
            
            # Create operation dict for validation
            operation = {
                "tool_name": tool_name,
                **params
            }
            
            validation_result = self.validator.validate_operation(operation, operation_type)
            if not validation_result:
                error_msg = f"Security validation failed: {validation_result.reason}"
                logger.warning(error_msg)
                if self.audit_logger:
                    self.audit_logger.log_operation(
                        operation_type="tool_execution",
                        operation=f"{tool_name}_security_blocked",
                        agent_id=agent_id,
                        success=False,
                        error=error_msg,
                        metadata={"tool_name": tool_name, "params": params, "reason": validation_result.reason}
                    )
                return ToolResult(
                    success=False,
                    output="",
                    error=error_msg,
                    metadata={"validation_result": validation_result.reason}
                )
        
        # Log operation start
        if self.audit_logger:
            self.audit_logger.log_operation(
                operation_type="tool_execution",
                operation=f"{tool_name}_start",
                agent_id=agent_id,
                success=True,
                metadata={"tool_name": tool_name, "params": params}
            )
        
        # Execute tool
        try:
            logger.info(f"Executing tool: {tool_name}")
            result = tool.execute(params)
            
            # Log operation completion
            if self.audit_logger:
                self.audit_logger.log_operation(
                    operation_type="tool_execution",
                    operation=f"{tool_name}_complete",
                    agent_id=agent_id,
                    success=result.success,
                    error=result.error,
                    metadata={
                        "tool_name": tool_name,
                        "output_length": len(result.output) if result.output else 0
                    }
                )
            
            if result.success:
                logger.info(f"Tool '{tool_name}' executed successfully")
            else:
                logger.warning(f"Tool '{tool_name}' execution failed: {result.error}")
            
            return result
            
        except Exception as e:
            error_msg = f"Tool execution error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            if self.audit_logger:
                self.audit_logger.log_operation(
                    operation_type="tool_execution",
                    operation=f"{tool_name}_error",
                    agent_id=agent_id,
                    success=False,
                    error=error_msg,
                    metadata={"tool_name": tool_name, "exception_type": type(e).__name__}
                )
            
            return ToolResult(
                success=False,
                output="",
                error=error_msg
            )
    
    def _detect_operation_type(self, tool_name: str, params: Dict[str, Any]) -> Optional[OperationType]:
        """
        Detect operation type from tool name and parameters.
        
        Args:
            tool_name: Name of the tool
            params: Tool parameters
            
        Returns:
            OperationType if detectable, None otherwise
        """
        if not SECURITY_AVAILABLE:
            return None
        
        tool_name_lower = tool_name.lower()
        
        # File operations
        if "read" in tool_name_lower or "file_read" in tool_name_lower:
            return OperationType.FILE_READ
        elif "write" in tool_name_lower or "file_write" in tool_name_lower:
            return OperationType.FILE_WRITE
        elif "delete" in tool_name_lower or "file_delete" in tool_name_lower:
            return OperationType.FILE_DELETE
        
        # Git operations
        if "git" in tool_name_lower:
            return OperationType.GIT_OPERATION
        
        # Command execution
        if "command" in tool_name_lower or "execute" in tool_name_lower:
            return OperationType.COMMAND
        
        return OperationType.COMMAND
