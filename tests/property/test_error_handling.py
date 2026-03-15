"""Property-based tests for error handling framework.

Feature: multi-agent-advisory-ai-system
"""

import pytest
from hypothesis import given, strategies as st, settings

from src.error_handling import ErrorClassifier, ErrorCategory


# Custom exception classes for testing
class ThrottlingException(Exception):
    """Simulated throttling exception."""
    pass


class ValidationException(Exception):
    """Simulated validation exception."""
    pass


class DataCorruptionException(Exception):
    """Simulated data corruption exception."""
    pass


class ServiceUnavailableException(Exception):
    """Simulated service unavailable exception."""
    pass


class ResourceNotFoundException(Exception):
    """Simulated resource not found exception."""
    pass


# Strategy for generating transient errors
@st.composite
def transient_error_strategy(draw):
    """Generate transient errors."""
    error_types = [
        ThrottlingException,
        ServiceUnavailableException,
        TimeoutError,
    ]
    error_messages = [
        "Request throttled",
        "Service temporarily unavailable",
        "Connection timeout",
        "Rate limit exceeded",
        "Too many requests"
    ]
    
    error_class = draw(st.sampled_from(error_types))
    message = draw(st.sampled_from(error_messages))
    return error_class(message)


# Strategy for generating permanent errors
@st.composite
def permanent_error_strategy(draw):
    """Generate permanent errors."""
    error_types = [
        ValidationException,
        ResourceNotFoundException,
        ValueError,
    ]
    error_messages = [
        "Invalid input parameter",
        "Resource not found",
        "Unauthorized access",
        "Malformed request",
        "Access denied"
    ]
    
    error_class = draw(st.sampled_from(error_types))
    message = draw(st.sampled_from(error_messages))
    return error_class(message)


# Strategy for generating critical errors
@st.composite
def critical_error_strategy(draw):
    """Generate critical errors."""
    error_types = [
        DataCorruptionException,
        RuntimeError,
    ]
    error_messages = [
        "Data corruption detected",
        "Security breach detected",
        "System failure",
        "Database unavailable",
        "Critical error in system"
    ]
    
    error_class = draw(st.sampled_from(error_types))
    message = draw(st.sampled_from(error_messages))
    return error_class(message)


class TestErrorCategorizationProperties:
    """Property-based tests for error categorization."""
    
    @settings(max_examples=100)
    @given(error=transient_error_strategy())
    def test_property_59_transient_errors_identified(self, error):
        """
        Property 59: Error Categorization and Retry Logic (Transient)
        
        For any error classified as transient, the error should be identified
        as transient and appropriate retry logic should be applied.
        
        **Validates: Requirements 14.3**
        """
        # Transient errors should be identified as transient
        assert ErrorClassifier.is_transient(error), \
            f"Error {error} should be classified as transient"
        
        # Transient errors should not be permanent
        assert not ErrorClassifier.is_permanent(error), \
            f"Transient error {error} should not be classified as permanent"
        
        # Category should be TRANSIENT (unless critical)
        category = ErrorClassifier.categorize(error)
        assert category in [ErrorCategory.TRANSIENT, ErrorCategory.CRITICAL], \
            f"Transient error should be categorized as TRANSIENT or CRITICAL, got {category}"
        
        # Should have recovery suggestions
        suggestions = ErrorClassifier.get_recovery_suggestions(error)
        assert len(suggestions) > 0, \
            f"Transient error should have recovery suggestions"
        
        # Should suggest retry
        suggestions_text = " ".join(suggestions).lower()
        assert "try again" in suggestions_text or "retry" in suggestions_text or "reduce" in suggestions_text, \
            f"Transient error suggestions should mention retry: {suggestions}"
    
    @settings(max_examples=100)
    @given(error=permanent_error_strategy())
    def test_property_59_permanent_errors_identified(self, error):
        """
        Property 59: Error Categorization and Retry Logic (Permanent)
        
        For any error classified as permanent, the error should be identified
        as permanent and retry logic should not be applied.
        
        **Validates: Requirements 14.3**
        """
        # Permanent errors should be identified as permanent
        assert ErrorClassifier.is_permanent(error), \
            f"Error {error} should be classified as permanent"
        
        # Permanent errors should not be transient
        assert not ErrorClassifier.is_transient(error), \
            f"Permanent error {error} should not be classified as transient"
        
        # Category should be PERMANENT (unless critical)
        category = ErrorClassifier.categorize(error)
        assert category in [ErrorCategory.PERMANENT, ErrorCategory.CRITICAL], \
            f"Permanent error should be categorized as PERMANENT or CRITICAL, got {category}"
        
        # Should have recovery suggestions
        suggestions = ErrorClassifier.get_recovery_suggestions(error)
        assert len(suggestions) > 0, \
            f"Permanent error should have recovery suggestions"
        
        # Should NOT suggest retry
        suggestions_text = " ".join(suggestions).lower()
        assert "try again" not in suggestions_text and "retry" not in suggestions_text, \
            f"Permanent error suggestions should not mention retry: {suggestions}"
    
    @settings(max_examples=100)
    @given(error=critical_error_strategy())
    def test_property_59_critical_errors_identified(self, error):
        """
        Property 59: Error Categorization and Retry Logic (Critical)
        
        For any error classified as critical, the error should be identified
        as critical and should trigger admin alerts.
        
        **Validates: Requirements 14.3**
        """
        # Critical errors should be identified as critical
        assert ErrorClassifier.is_critical(error), \
            f"Error {error} should be classified as critical"
        
        # Category should be CRITICAL
        category = ErrorClassifier.categorize(error)
        assert category == ErrorCategory.CRITICAL, \
            f"Critical error should be categorized as CRITICAL, got {category}"
        
        # Should have recovery suggestions
        suggestions = ErrorClassifier.get_recovery_suggestions(error)
        assert len(suggestions) > 0, \
            f"Critical error should have recovery suggestions"
        
        # Should mention contacting admin
        suggestions_text = " ".join(suggestions).lower()
        assert "administrator" in suggestions_text or "admin" in suggestions_text, \
            f"Critical error suggestions should mention administrator: {suggestions}"
        
        # Should warn against retry
        assert "do not retry" in suggestions_text or "not retry" in suggestions_text, \
            f"Critical error suggestions should warn against retry: {suggestions}"
    
    @settings(max_examples=100)
    @given(
        error_type=st.sampled_from([
            ThrottlingException,
            ValidationException,
            DataCorruptionException,
            ServiceUnavailableException,
            ResourceNotFoundException
        ]),
        message=st.text(min_size=1, max_size=100)
    )
    def test_property_categorization_consistency(self, error_type, message):
        """
        Property: Error categorization should be consistent.
        
        For any error, categorizing it multiple times should produce
        the same result.
        """
        error = error_type(message)
        
        # Categorize multiple times
        category1 = ErrorClassifier.categorize(error)
        category2 = ErrorClassifier.categorize(error)
        category3 = ErrorClassifier.categorize(error)
        
        # Should be consistent
        assert category1 == category2 == category3, \
            f"Error categorization should be consistent"
    
    @settings(max_examples=100)
    @given(
        error_type=st.sampled_from([
            ThrottlingException,
            ValidationException,
            DataCorruptionException
        ]),
        message=st.text(min_size=1, max_size=100)
    )
    def test_property_recovery_suggestions_non_empty(self, error_type, message):
        """
        Property: All errors should have recovery suggestions.
        
        For any error, the system should provide at least one
        recovery suggestion.
        """
        error = error_type(message)
        suggestions = ErrorClassifier.get_recovery_suggestions(error)
        
        assert len(suggestions) > 0, \
            f"Error should have at least one recovery suggestion"
        
        # All suggestions should be non-empty strings
        for suggestion in suggestions:
            assert isinstance(suggestion, str), \
                f"Recovery suggestion should be a string"
            assert len(suggestion) > 0, \
                f"Recovery suggestion should not be empty"
    
    def test_property_mutually_exclusive_categories(self):
        """
        Property: Error categories should be mutually exclusive.
        
        An error should not be classified as both transient and permanent
        at the same time (though it can be critical and one of the others).
        """
        # Test with known error types
        test_errors = [
            (ThrottlingException("throttled"), True, False),
            (ValidationException("invalid"), False, True),
            (ResourceNotFoundException("not found"), False, True),
            (ServiceUnavailableException("unavailable"), True, False),
        ]
        
        for error, should_be_transient, should_be_permanent in test_errors:
            is_transient = ErrorClassifier.is_transient(error)
            is_permanent = ErrorClassifier.is_permanent(error)
            
            # Check expected classification
            assert is_transient == should_be_transient, \
                f"Error {error} transient classification incorrect"
            assert is_permanent == should_be_permanent, \
                f"Error {error} permanent classification incorrect"
            
            # Should not be both transient and permanent
            assert not (is_transient and is_permanent), \
                f"Error {error} should not be both transient and permanent"


class TestErrorCategorizationEdgeCases:
    """Test edge cases for error categorization."""
    
    def test_unknown_error_defaults_to_transient(self):
        """Unknown errors should default to transient (safer to retry)."""
        class UnknownError(Exception):
            pass
        
        error = UnknownError("Something unexpected happened")
        category = ErrorClassifier.categorize(error)
        
        # Should default to transient
        assert category == ErrorCategory.TRANSIENT, \
            f"Unknown error should default to TRANSIENT, got {category}"
    
    def test_error_with_empty_message(self):
        """Errors with empty messages should still be categorized."""
        error = ValidationException("")
        
        # Should still be categorized as permanent based on type
        assert ErrorClassifier.is_permanent(error), \
            f"ValidationException with empty message should be permanent"
        
        category = ErrorClassifier.categorize(error)
        assert category == ErrorCategory.PERMANENT, \
            f"ValidationException should be PERMANENT, got {category}"
    
    def test_error_with_mixed_signals(self):
        """
        Errors with mixed signals (e.g., ValidationException with 'timeout' message)
        should be categorized by type first.
        """
        # Permanent type with transient message
        error = ValidationException("Connection timeout")
        
        # Type should take precedence
        assert ErrorClassifier.is_permanent(error), \
            f"ValidationException should be permanent regardless of message"
        
        category = ErrorClassifier.categorize(error)
        assert category == ErrorCategory.PERMANENT, \
            f"ValidationException should be PERMANENT, got {category}"
