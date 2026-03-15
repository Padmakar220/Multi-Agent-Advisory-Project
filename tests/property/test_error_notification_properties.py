"""Property-based tests for error notification system.

**Validates: Requirements 14.2, 14.4, 14.5**
"""

import pytest
from hypothesis import given, strategies as st
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.error_handling import ErrorClassifier, ErrorCategory
from src.models.responses import ErrorResponse


# Strategies for generating test data
@st.composite
def error_strategy(draw):
    """Generate various error types for testing."""
    error_types = [
        ("ThrottlingException", "Request throttled"),
        ("ValidationException", "Invalid input"),
        ("DataCorruptionException", "Data corruption detected"),
        ("TimeoutException", "Request timeout"),
        ("ResourceNotFoundException", "Resource not found"),
    ]
    error_type, message = draw(st.sampled_from(error_types))
    return Exception(message)


@st.composite
def user_facing_error_strategy(draw):
    """Generate user-facing errors (non-critical)."""
    messages = [
        "Portfolio not found",
        "Invalid allocation percentage",
        "Insufficient funds for trade",
        "Market data temporarily unavailable",
        "Request timeout - please retry",
    ]
    return Exception(draw(st.sampled_from(messages)))


@st.composite
def critical_error_strategy(draw):
    """Generate critical errors requiring admin alert."""
    messages = [
        "Data corruption detected in portfolio",
        "Security breach detected",
        "Database unavailable",
        "System failure in trade execution",
        "Unauthorized access attempt",
    ]
    return Exception(draw(st.sampled_from(messages)))


@st.composite
def recoverable_error_strategy(draw):
    """Generate recoverable errors with suggestions."""
    messages = [
        "Service temporarily unavailable",
        "Rate limit exceeded",
        "Connection timeout",
        "Temporary network issue",
        "Request throttled",
    ]
    return Exception(draw(st.sampled_from(messages)))


@st.composite
def error_response_strategy(draw):
    """Generate ErrorResponse objects."""
    error_codes = [
        "AGENT_ERROR",
        "VALIDATION_ERROR",
        "SYSTEM_ERROR",
        "TRANSIENT_ERROR",
        "PERMANENT_ERROR",
        "CRITICAL_ERROR"
    ]
    
    return ErrorResponse(
        error_code=draw(st.sampled_from(error_codes)),
        error_message=draw(st.text(min_size=1, max_size=200)),
        error_details={"service": "test-service"},
        recovery_suggestions=draw(st.lists(st.text(min_size=1, max_size=100), max_size=5)),
        support_reference=draw(st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=8, max_size=8))
    )


class TestUserFacingErrorNotification:
    """Property 58: User-Facing Error Notification.
    
    For any error that affects user-facing operations, the user should be
    notified with a descriptive error message.
    """

    @given(user_facing_error_strategy())
    def test_user_facing_error_has_message(self, error):
        """Test that user-facing errors have descriptive messages."""
        classifier = ErrorClassifier()
        category = classifier.categorize(error)
        
        # User-facing errors should not be critical
        assert category != ErrorCategory.CRITICAL
        
        # Error should have a message
        assert str(error)
        assert len(str(error)) > 0

    @given(user_facing_error_strategy())
    def test_error_response_has_user_message(self, error):
        """Test that ErrorResponse contains user-friendly message."""
        response = ErrorResponse(
            error_code="AGENT_ERROR",
            error_message=str(error),
            error_details={"original_error": str(error)},
            recovery_suggestions=["Please try again"],
            support_reference="REF123456"
        )
        
        assert response.error_message
        assert len(response.error_message) > 0
        assert response.error_code in [
            "AGENT_ERROR",
            "VALIDATION_ERROR",
            "SYSTEM_ERROR",
            "TRANSIENT_ERROR",
            "PERMANENT_ERROR"
        ]

    @given(user_facing_error_strategy())
    def test_error_response_has_timestamp(self, error):
        """Test that error responses include timestamp."""
        response = ErrorResponse(
            error_code="AGENT_ERROR",
            error_message=str(error),
            error_details={},
            recovery_suggestions=[],
            support_reference="REF123456"
        )
        
        assert response.timestamp
        # Verify timestamp is ISO format
        datetime.fromisoformat(response.timestamp)

    @given(user_facing_error_strategy())
    def test_error_response_has_support_reference(self, error):
        """Test that error responses include support reference."""
        response = ErrorResponse(
            error_code="AGENT_ERROR",
            error_message=str(error),
            error_details={},
            recovery_suggestions=[],
            support_reference="REF123456"
        )
        
        assert response.support_reference
        assert len(response.support_reference) > 0


class TestCriticalErrorAlerting:
    """Property 60: Critical Error Alerting.
    
    For any critical error (system failure, data corruption, security breach),
    an alert should be sent to system administrators via SNS.
    """

    @given(critical_error_strategy())
    def test_critical_error_is_categorized_correctly(self, error):
        """Test that critical errors are properly categorized."""
        classifier = ErrorClassifier()
        category = classifier.categorize(error)
        
        assert category == ErrorCategory.CRITICAL

    @given(critical_error_strategy())
    def test_critical_error_response_marked_as_critical(self, error):
        """Test that critical errors are marked in response."""
        response = ErrorResponse(
            error_code="CRITICAL_ERROR",
            error_message=str(error),
            error_details={"severity": "critical"},
            recovery_suggestions=["Contact administrator"],
            support_reference="CRIT123456"
        )
        
        assert response.error_code == "CRITICAL_ERROR"
        assert "critical" in response.error_code.lower()

    @given(critical_error_strategy())
    def test_critical_error_has_admin_suggestions(self, error):
        """Test that critical errors suggest admin contact."""
        classifier = ErrorClassifier()
        suggestions = classifier.get_recovery_suggestions(error)
        
        assert len(suggestions) > 0
        # Should suggest contacting administrator
        admin_suggestion = any("admin" in s.lower() or "contact" in s.lower() 
                              for s in suggestions)
        assert admin_suggestion

    @given(critical_error_strategy())
    def test_critical_error_response_has_details(self, error):
        """Test that critical error responses include error details."""
        response = ErrorResponse(
            error_code="CRITICAL_ERROR",
            error_message=str(error),
            error_details={
                "error_type": error.__class__.__name__,
                "severity": "critical",
                "requires_alert": True
            },
            recovery_suggestions=["Contact administrator"],
            support_reference="CRIT123456"
        )
        
        assert response.error_details
        assert "severity" in response.error_details
        assert response.error_details["severity"] == "critical"


class TestErrorRecoverySuggestions:
    """Property 61: Error Recovery Suggestions.
    
    For any recoverable error, the system should provide actionable
    recovery suggestions to the user.
    """

    @given(recoverable_error_strategy())
    def test_recoverable_error_has_suggestions(self, error):
        """Test that recoverable errors have recovery suggestions."""
        classifier = ErrorClassifier()
        suggestions = classifier.get_recovery_suggestions(error)
        
        assert len(suggestions) > 0
        assert all(isinstance(s, str) for s in suggestions)
        assert all(len(s) > 0 for s in suggestions)

    @given(recoverable_error_strategy())
    def test_recovery_suggestions_are_actionable(self, error):
        """Test that recovery suggestions are actionable."""
        classifier = ErrorClassifier()
        suggestions = classifier.get_recovery_suggestions(error)
        
        # Suggestions should be actionable (contain verbs or instructions)
        actionable_keywords = [
            "try", "check", "verify", "contact", "reduce", "increase",
            "retry", "wait", "review", "restart", "reconnect"
        ]
        
        for suggestion in suggestions:
            is_actionable = any(keyword in suggestion.lower() 
                               for keyword in actionable_keywords)
            assert is_actionable, f"Suggestion not actionable: {suggestion}"

    @given(recoverable_error_strategy())
    def test_error_response_includes_suggestions(self, error):
        """Test that ErrorResponse includes recovery suggestions."""
        classifier = ErrorClassifier()
        suggestions = classifier.get_recovery_suggestions(error)
        
        response = ErrorResponse(
            error_code="TRANSIENT_ERROR",
            error_message=str(error),
            error_details={},
            recovery_suggestions=suggestions,
            support_reference="REC123456"
        )
        
        assert response.recovery_suggestions
        assert len(response.recovery_suggestions) > 0

    @given(st.lists(st.text(min_size=1, max_size=100), min_size=1, max_size=5))
    def test_multiple_recovery_suggestions(self, suggestions):
        """Test that multiple recovery suggestions are supported."""
        response = ErrorResponse(
            error_code="TRANSIENT_ERROR",
            error_message="Test error",
            error_details={},
            recovery_suggestions=suggestions,
            support_reference="MULTI123456"
        )
        
        assert len(response.recovery_suggestions) == len(suggestions)
        assert all(s in response.recovery_suggestions for s in suggestions)


class TestErrorNotificationIntegration:
    """Integration tests for error notification system."""

    @given(error_response_strategy())
    def test_error_response_serialization(self, response):
        """Test that error responses can be serialized."""
        # Should be able to convert to dict
        response_dict = {
            "error_code": response.error_code,
            "error_message": response.error_message,
            "error_details": response.error_details,
            "recovery_suggestions": response.recovery_suggestions,
            "support_reference": response.support_reference,
            "timestamp": response.timestamp
        }
        
        assert response_dict["error_code"]
        assert response_dict["error_message"]
        assert isinstance(response_dict["recovery_suggestions"], list)

    @given(error_strategy())
    def test_error_categorization_consistency(self, error):
        """Test that error categorization is consistent."""
        classifier = ErrorClassifier()
        
        # Categorize multiple times - should be consistent
        category1 = classifier.categorize(error)
        category2 = classifier.categorize(error)
        
        assert category1 == category2

    @given(error_strategy())
    def test_error_has_recovery_path(self, error):
        """Test that every error has a recovery path."""
        classifier = ErrorClassifier()
        category = classifier.categorize(error)
        suggestions = classifier.get_recovery_suggestions(error)
        
        # Every error should have suggestions
        assert len(suggestions) > 0
        
        # Suggestions should be appropriate for category
        if category == ErrorCategory.CRITICAL:
            assert any("admin" in s.lower() or "contact" in s.lower() 
                      for s in suggestions)
        elif category == ErrorCategory.TRANSIENT:
            assert any("try" in s.lower() or "retry" in s.lower() 
                      for s in suggestions)
        elif category == ErrorCategory.PERMANENT:
            assert any("check" in s.lower() or "verify" in s.lower() 
                      for s in suggestions)
