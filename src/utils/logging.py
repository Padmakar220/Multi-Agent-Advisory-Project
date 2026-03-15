"""Structured logging utilities for CloudWatch."""

import json
import logging
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from contextvars import ContextVar

# Context variable for trace ID propagation
trace_id_var: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)


class StructuredLogger:
    """
    Structured logger that outputs JSON format for CloudWatch.
    
    Includes timestamp, level, service name, user_id, trace_id, and message.
    """
    
    def __init__(self, service_name: str, log_level: str = "INFO"):
        """
        Initialize structured logger.
        
        Args:
            service_name: Name of the service (e.g., "portfolio-analyzer")
            log_level: Logging level (DEBUG, INFO, WARN, ERROR, CRITICAL)
        """
        self.service_name = service_name
        self.logger = logging.getLogger(service_name)
        
        # Set log level
        level = getattr(logging, log_level.upper(), logging.INFO)
        self.logger.setLevel(level)
        
        # Configure handler for JSON output
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        self.logger.addHandler(handler)
        
        # Prevent duplicate logs
        self.logger.propagate = False
    
    def _create_log_entry(
        self,
        level: str,
        message: str,
        user_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create structured log entry.
        
        Args:
            level: Log level
            message: Log message
            user_id: Optional user ID
            **kwargs: Additional context fields
            
        Returns:
            Dictionary with log entry fields
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "service": self.service_name,
            "message": message
        }
        
        # Add trace ID if available
        trace_id = trace_id_var.get()
        if trace_id:
            entry["trace_id"] = trace_id
        
        # Add user ID if provided
        if user_id:
            entry["user_id"] = user_id
        
        # Add any additional context
        if kwargs:
            entry["context"] = kwargs
        
        return entry
    
    def debug(self, message: str, user_id: Optional[str] = None, **kwargs):
        """Log debug message."""
        entry = self._create_log_entry("DEBUG", message, user_id, **kwargs)
        self.logger.debug(json.dumps(entry))
    
    def info(self, message: str, user_id: Optional[str] = None, **kwargs):
        """Log info message."""
        entry = self._create_log_entry("INFO", message, user_id, **kwargs)
        self.logger.info(json.dumps(entry))
    
    def warn(self, message: str, user_id: Optional[str] = None, **kwargs):
        """Log warning message."""
        entry = self._create_log_entry("WARN", message, user_id, **kwargs)
        self.logger.warning(json.dumps(entry))
    
    def error(self, message: str, user_id: Optional[str] = None, **kwargs):
        """Log error message."""
        entry = self._create_log_entry("ERROR", message, user_id, **kwargs)
        self.logger.error(json.dumps(entry))
    
    def critical(self, message: str, user_id: Optional[str] = None, **kwargs):
        """Log critical message."""
        entry = self._create_log_entry("CRITICAL", message, user_id, **kwargs)
        self.logger.critical(json.dumps(entry))
    
    def log_error_with_exception(
        self,
        message: str,
        error: Exception,
        user_id: Optional[str] = None,
        **kwargs
    ):
        """
        Log error with exception details.
        
        Args:
            message: Error message
            error: Exception object
            user_id: Optional user ID
            **kwargs: Additional context
        """
        error_context = {
            "error_type": error.__class__.__name__,
            "error_message": str(error),
            **kwargs
        }
        self.error(message, user_id, **error_context)


class JsonFormatter(logging.Formatter):
    """Custom formatter that outputs JSON."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string."""
        # The message is already JSON from StructuredLogger
        return record.getMessage()


class TraceContext:
    """Context manager for trace ID propagation."""
    
    def __init__(self, trace_id: str):
        """
        Initialize trace context.
        
        Args:
            trace_id: Trace ID to propagate
        """
        self.trace_id = trace_id
        self.token = None
    
    def __enter__(self):
        """Set trace ID in context."""
        self.token = trace_id_var.set(self.trace_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Reset trace ID context."""
        if self.token:
            trace_id_var.reset(self.token)


def set_trace_id(trace_id: str):
    """
    Set trace ID for current context.
    
    Args:
        trace_id: Trace ID to set
    """
    trace_id_var.set(trace_id)


def get_trace_id() -> Optional[str]:
    """
    Get trace ID from current context.
    
    Returns:
        Current trace ID or None
    """
    return trace_id_var.get()


def create_logger(service_name: str, log_level: str = "INFO") -> StructuredLogger:
    """
    Create a structured logger instance.
    
    Args:
        service_name: Name of the service
        log_level: Logging level
        
    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(service_name, log_level)
