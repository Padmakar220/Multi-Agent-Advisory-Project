"""Error classification and handling utilities."""

from typing import Dict, List, Optional
from enum import Enum


class ErrorCategory(Enum):
    """Error categories for classification."""
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    CRITICAL = "critical"


class ErrorClassifier:
    """Classifies errors into transient, permanent, or critical categories."""
    
    # Error types that are transient (should be retried)
    TRANSIENT_ERROR_TYPES = {
        "ThrottlingException",
        "ServiceUnavailableException",
        "TimeoutException",
        "ProvisionedThroughputExceededException",
        "RequestLimitExceeded",
        "TooManyRequestsException",
        "InternalServerError",
        "ServiceException"
    }
    
    # Error types that are permanent (should not be retried)
    PERMANENT_ERROR_TYPES = {
        "ValidationException",
        "AuthenticationException",
        "AuthorizationException",
        "InvalidInputException",
        "ResourceNotFoundException",
        "InvalidParameterException",
        "InvalidRequestException",
        "AccessDeniedException"
    }
    
    # Error types that are critical (require admin alert)
    CRITICAL_ERROR_TYPES = {
        "DataCorruptionException",
        "SecurityException",
        "UnauthorizedAccessException",
        "SystemFailureException",
        "DatabaseUnavailableException"
    }
    
    @classmethod
    def is_transient(cls, error: Exception) -> bool:
        """
        Determine if an error is transient and should be retried.
        
        Args:
            error: The exception to classify
            
        Returns:
            True if the error is transient, False otherwise
        """
        error_type = error.__class__.__name__
        error_message = str(error).lower()
        
        # Check by error type
        if error_type in cls.TRANSIENT_ERROR_TYPES:
            return True
        
        # Check by error message patterns
        transient_patterns = [
            "timeout",
            "throttl",
            "rate limit",
            "too many requests",
            "service unavailable",
            "temporarily unavailable",
            "connection reset",
            "connection refused"
        ]
        
        return any(pattern in error_message for pattern in transient_patterns)
    
    @classmethod
    def is_permanent(cls, error: Exception) -> bool:
        """
        Determine if an error is permanent and should not be retried.
        
        Args:
            error: The exception to classify
            
        Returns:
            True if the error is permanent, False otherwise
        """
        error_type = error.__class__.__name__
        error_message = str(error).lower()
        
        # Check by error type
        if error_type in cls.PERMANENT_ERROR_TYPES:
            return True
        
        # Check by error message patterns
        permanent_patterns = [
            "invalid",
            "not found",
            "does not exist",
            "unauthorized",
            "forbidden",
            "access denied",
            "authentication failed",
            "malformed"
        ]
        
        return any(pattern in error_message for pattern in permanent_patterns)
    
    @classmethod
    def is_critical(cls, error: Exception) -> bool:
        """
        Determine if an error is critical and requires admin alert.
        
        Args:
            error: The exception to classify
            
        Returns:
            True if the error is critical, False otherwise
        """
        error_type = error.__class__.__name__
        error_message = str(error).lower()
        
        # Check by error type
        if error_type in cls.CRITICAL_ERROR_TYPES:
            return True
        
        # Check by error message patterns
        critical_patterns = [
            "data corruption",
            "security breach",
            "system failure",
            "database unavailable",
            "critical error"
        ]
        
        return any(pattern in error_message for pattern in critical_patterns)
    
    @classmethod
    def categorize(cls, error: Exception) -> ErrorCategory:
        """
        Categorize an error into transient, permanent, or critical.
        
        Args:
            error: The exception to categorize
            
        Returns:
            ErrorCategory enum value
        """
        if cls.is_critical(error):
            return ErrorCategory.CRITICAL
        elif cls.is_transient(error):
            return ErrorCategory.TRANSIENT
        elif cls.is_permanent(error):
            return ErrorCategory.PERMANENT
        else:
            # Default to transient for unknown errors (safer to retry)
            return ErrorCategory.TRANSIENT
    
    @classmethod
    def get_recovery_suggestions(cls, error: Exception) -> List[str]:
        """
        Get recovery suggestions for an error.
        
        Args:
            error: The exception to get suggestions for
            
        Returns:
            List of recovery suggestion strings
        """
        category = cls.categorize(error)
        error_message = str(error).lower()
        
        if category == ErrorCategory.TRANSIENT:
            suggestions = ["Please try again in a few moments"]
            
            if "throttl" in error_message or "rate limit" in error_message:
                suggestions.append("Reduce request frequency")
            elif "timeout" in error_message:
                suggestions.append("Check network connectivity")
                
            return suggestions
        
        elif category == ErrorCategory.PERMANENT:
            suggestions = []
            
            if "invalid" in error_message or "malformed" in error_message:
                suggestions.append("Check input parameters and format")
            elif "not found" in error_message:
                suggestions.append("Verify the resource exists")
            elif "unauthorized" in error_message or "access denied" in error_message:
                suggestions.append("Check authentication credentials")
                suggestions.append("Verify you have necessary permissions")
            else:
                suggestions.append("Review request parameters")
                
            return suggestions
        
        else:  # CRITICAL
            return [
                "Contact system administrator immediately",
                "Do not retry this operation"
            ]
