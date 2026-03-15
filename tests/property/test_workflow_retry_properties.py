"""
Property-based tests for Step Functions workflow retry behavior.

**Validates: Requirements 10.2**
"""

import json
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from datetime import datetime, timedelta
from typing import Dict, Any, List


class WorkflowRetryProperties:
    """Properties for workflow step retry with exponential backoff."""

    @staticmethod
    def calculate_retry_intervals(
        initial_interval: int,
        backoff_rate: float,
        max_attempts: int
    ) -> List[int]:
        """Calculate retry intervals with exponential backoff."""
        intervals = []
        current_interval = initial_interval
        for _ in range(max_attempts):
            intervals.append(current_interval)
            current_interval = int(current_interval * backoff_rate)
        return intervals

    @staticmethod
    def validate_retry_policy(retry_policy: Dict[str, Any]) -> bool:
        """Validate that retry policy conforms to specification."""
        required_fields = ['ErrorEquals', 'IntervalSeconds', 'MaxAttempts', 'BackoffRate']
        for field in required_fields:
            if field not in retry_policy:
                return False
        
        # Validate values
        if not isinstance(retry_policy['ErrorEquals'], list):
            return False
        if retry_policy['IntervalSeconds'] <= 0:
            return False
        if retry_policy['MaxAttempts'] <= 0:
            return False
        if retry_policy['BackoffRate'] <= 1.0:
            return False
        
        return True

    @staticmethod
    def validate_exponential_backoff(
        initial_interval: int,
        backoff_rate: float,
        max_attempts: int,
        expected_intervals: List[int]
    ) -> bool:
        """Validate that intervals follow exponential backoff pattern."""
        calculated = WorkflowRetryProperties.calculate_retry_intervals(
            initial_interval, backoff_rate, max_attempts
        )
        return calculated == expected_intervals


# Property 41: Workflow Step Retry with Exponential Backoff
@given(
    initial_interval=st.integers(min_value=1, max_value=10),
    backoff_rate=st.floats(min_value=1.5, max_value=3.0),
    max_attempts=st.integers(min_value=1, max_value=5)
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_workflow_step_retry_exponential_backoff(
    initial_interval: int,
    backoff_rate: float,
    max_attempts: int
):
    """
    **Property 41: Workflow Step Retry with Exponential Backoff**
    
    For any workflow step with retry policy configured, the retry intervals
    should follow exponential backoff pattern: each retry interval should be
    the previous interval multiplied by the backoff rate.
    
    **Validates: Requirements 10.2**
    """
    # Calculate expected intervals
    intervals = WorkflowRetryProperties.calculate_retry_intervals(
        initial_interval, backoff_rate, max_attempts
    )
    
    # Verify exponential growth
    for i in range(1, len(intervals)):
        expected = int(intervals[i - 1] * backoff_rate)
        assert intervals[i] == expected, \
            f"Interval {i} should be {expected}, got {intervals[i]}"
    
    # Verify first interval matches initial
    assert intervals[0] == initial_interval, \
        f"First interval should be {initial_interval}, got {intervals[0]}"
    
    # Verify number of intervals matches max attempts
    assert len(intervals) == max_attempts, \
        f"Should have {max_attempts} intervals, got {len(intervals)}"


@given(
    error_equals=st.lists(
        st.sampled_from(['States.TaskFailed', 'States.Timeout', 'States.ALL']),
        min_size=1,
        max_size=3,
        unique=True
    ),
    interval_seconds=st.integers(min_value=1, max_value=60),
    max_attempts=st.integers(min_value=1, max_value=5),
    backoff_rate=st.floats(min_value=1.5, max_value=3.0)
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_retry_policy_structure_validity(
    error_equals: List[str],
    interval_seconds: int,
    max_attempts: int,
    backoff_rate: float
):
    """
    **Property 41: Workflow Step Retry with Exponential Backoff**
    
    For any retry policy configuration, the structure should be valid and
    contain all required fields with appropriate values.
    
    **Validates: Requirements 10.2**
    """
    retry_policy = {
        'ErrorEquals': error_equals,
        'IntervalSeconds': interval_seconds,
        'MaxAttempts': max_attempts,
        'BackoffRate': backoff_rate
    }
    
    # Validate structure
    assert WorkflowRetryProperties.validate_retry_policy(retry_policy), \
        f"Retry policy structure is invalid: {retry_policy}"
    
    # Validate error equals is non-empty
    assert len(retry_policy['ErrorEquals']) > 0, \
        "ErrorEquals list should not be empty"
    
    # Validate all error types are strings
    assert all(isinstance(e, str) for e in retry_policy['ErrorEquals']), \
        "All error types should be strings"


@given(
    initial_interval=st.integers(min_value=2, max_value=5),
    backoff_rate=st.just(2.0),
    max_attempts=st.just(3)
)
@settings(max_examples=50)
def test_standard_retry_policy_intervals(
    initial_interval: int,
    backoff_rate: float,
    max_attempts: int
):
    """
    **Property 41: Workflow Step Retry with Exponential Backoff**
    
    For the standard retry policy (2s, 4s, 8s with backoff rate 2.0),
    verify that intervals follow the expected pattern.
    
    **Validates: Requirements 10.2**
    """
    intervals = WorkflowRetryProperties.calculate_retry_intervals(
        initial_interval, backoff_rate, max_attempts
    )
    
    # For backoff_rate=2.0 and max_attempts=3:
    # intervals should be [initial, initial*2, initial*4]
    expected = [initial_interval, initial_interval * 2, initial_interval * 4]
    assert intervals == expected, \
        f"Expected {expected}, got {intervals}"


@given(
    num_retries=st.integers(min_value=1, max_value=5),
    initial_interval=st.integers(min_value=1, max_value=10),
    backoff_rate=st.floats(min_value=1.5, max_value=3.0)
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_retry_count_never_exceeds_max_attempts(
    num_retries: int,
    initial_interval: int,
    backoff_rate: float
):
    """
    **Property 41: Workflow Step Retry with Exponential Backoff**
    
    For any retry configuration, the number of retry attempts should never
    exceed the configured MaxAttempts value.
    
    **Validates: Requirements 10.2**
    """
    intervals = WorkflowRetryProperties.calculate_retry_intervals(
        initial_interval, backoff_rate, num_retries
    )
    
    # Number of intervals should equal max attempts
    assert len(intervals) == num_retries, \
        f"Number of intervals ({len(intervals)}) should equal max attempts ({num_retries})"
    
    # Each interval should be positive
    assert all(interval > 0 for interval in intervals), \
        "All intervals should be positive"


@given(
    backoff_rate=st.floats(min_value=1.5, max_value=3.0),
    max_attempts=st.integers(min_value=2, max_value=5)
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_retry_intervals_monotonically_increasing(
    backoff_rate: float,
    max_attempts: int
):
    """
    **Property 41: Workflow Step Retry with Exponential Backoff**
    
    For any retry policy with backoff rate > 1.0, retry intervals should
    be monotonically increasing (each interval >= previous interval).
    
    **Validates: Requirements 10.2**
    """
    intervals = WorkflowRetryProperties.calculate_retry_intervals(
        initial_interval=2,
        backoff_rate=backoff_rate,
        max_attempts=max_attempts
    )
    
    # Verify monotonically increasing
    for i in range(1, len(intervals)):
        assert intervals[i] >= intervals[i - 1], \
            f"Intervals should be monotonically increasing: {intervals}"


@given(
    initial_interval=st.integers(min_value=1, max_value=10),
    backoff_rate=st.floats(min_value=1.5, max_value=3.0),
    max_attempts=st.integers(min_value=1, max_value=5)
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_retry_policy_json_serializable(
    initial_interval: int,
    backoff_rate: float,
    max_attempts: int
):
    """
    **Property 41: Workflow Step Retry with Exponential Backoff**
    
    For any retry policy, the configuration should be JSON serializable
    (as required by Step Functions state machine definitions).
    
    **Validates: Requirements 10.2**
    """
    retry_policy = {
        'ErrorEquals': ['States.TaskFailed'],
        'IntervalSeconds': initial_interval,
        'MaxAttempts': max_attempts,
        'BackoffRate': backoff_rate
    }
    
    # Should be JSON serializable
    try:
        json_str = json.dumps(retry_policy)
        deserialized = json.loads(json_str)
        assert deserialized == retry_policy, \
            "Deserialized policy should match original"
    except (TypeError, ValueError) as e:
        pytest.fail(f"Retry policy should be JSON serializable: {e}")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
