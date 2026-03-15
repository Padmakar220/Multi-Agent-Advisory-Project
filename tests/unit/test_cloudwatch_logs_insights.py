"""Unit tests for CloudWatch Logs Insights query management."""

import pytest
from unittest.mock import MagicMock, patch
from src.utils.cloudwatch_logs_insights import (
    CloudWatchLogsInsights,
    create_logs_insights_client
)


@pytest.fixture
def logs_insights_client():
    """Create a Logs Insights client with mocked boto3 client."""
    with patch("boto3.client") as mock_client:
        client = CloudWatchLogsInsights(region="us-east-1")
        client.client = MagicMock()
        yield client


class TestCloudWatchLogsInsights:
    """Tests for CloudWatchLogsInsights class."""

    def test_init(self):
        """Test Logs Insights client initialization."""
        with patch("boto3.client"):
            client = CloudWatchLogsInsights(region="us-west-2")
            assert client.region == "us-west-2"

    def test_start_query_success(self, logs_insights_client):
        """Test successful query start."""
        logs_insights_client.client.start_query.return_value = {
            "queryId": "query-123"
        }
        
        result = logs_insights_client.start_query(
            log_group_name="/aws/lambda/test",
            query="fields @timestamp | limit 10",
            start_time=1000,
            end_time=2000
        )
        
        assert result == "query-123"
        logs_insights_client.client.start_query.assert_called_once()

    def test_start_query_failure(self, logs_insights_client):
        """Test query start failure."""
        logs_insights_client.client.start_query.side_effect = Exception("API Error")
        
        result = logs_insights_client.start_query(
            log_group_name="/aws/lambda/test",
            query="fields @timestamp",
            start_time=1000,
            end_time=2000
        )
        
        assert result is None

    def test_get_query_results_success(self, logs_insights_client):
        """Test successful query results retrieval."""
        logs_insights_client.client.get_query_results.return_value = {
            "status": "Complete",
            "results": [
                [
                    {"field": "@timestamp", "value": "2024-01-15T10:00:00Z"},
                    {"field": "@message", "value": "Test message"}
                ]
            ],
            "statistics": {"recordsMatched": 1}
        }
        
        result = logs_insights_client.get_query_results("query-123")
        
        assert result is not None
        assert result["status"] == "Complete"
        assert len(result["results"]) == 1
        assert result["statistics"]["recordsMatched"] == 1

    def test_get_query_results_failure(self, logs_insights_client):
        """Test query results retrieval failure."""
        logs_insights_client.client.get_query_results.side_effect = Exception("API Error")
        
        result = logs_insights_client.get_query_results("query-123")
        
        assert result is None

    def test_stop_query_success(self, logs_insights_client):
        """Test successful query stop."""
        logs_insights_client.client.stop_query.return_value = {}
        
        result = logs_insights_client.stop_query("query-123")
        
        assert result is True
        logs_insights_client.client.stop_query.assert_called_once_with(queryId="query-123")

    def test_stop_query_failure(self, logs_insights_client):
        """Test query stop failure."""
        logs_insights_client.client.stop_query.side_effect = Exception("API Error")
        
        result = logs_insights_client.stop_query("query-123")
        
        assert result is False

    def test_get_error_analysis_query(self, logs_insights_client):
        """Test error analysis query generation."""
        query = logs_insights_client.get_error_analysis_query()
        
        assert "ERROR" in query
        assert "CRITICAL" in query
        assert "FATAL" in query
        assert "service" in query
        assert "error_type" in query
        assert "stats count()" in query

    def test_get_user_activity_query(self, logs_insights_client):
        """Test user activity query generation."""
        query = logs_insights_client.get_user_activity_query()
        
        assert "user_id" in query
        assert "action" in query
        assert "resource" in query
        assert "status" in query
        assert "duration" in query
        assert "stats count()" in query

    def test_get_trade_execution_audit_query(self, logs_insights_client):
        """Test trade execution audit query generation."""
        query = logs_insights_client.get_trade_execution_audit_query()
        
        assert "trade_id" in query
        assert "ticker" in query
        assert "quantity" in query
        assert "price" in query
        assert "status" in query
        assert "execution_time" in query

    def test_run_error_analysis_success(self, logs_insights_client):
        """Test successful error analysis query execution."""
        logs_insights_client.client.start_query.return_value = {"queryId": "query-123"}
        logs_insights_client.client.get_query_results.return_value = {
            "status": "Complete",
            "results": [
                [
                    {"field": "service", "value": "portfolio-analyzer"},
                    {"field": "error_count", "value": "5"}
                ]
            ],
            "statistics": {}
        }
        
        result = logs_insights_client.run_error_analysis(
            log_group_name="/aws/lambda/test",
            start_time=1000,
            end_time=2000
        )
        
        assert result is not None
        assert result["status"] == "Complete"
        assert len(result["results"]) == 1

    def test_run_error_analysis_failure(self, logs_insights_client):
        """Test error analysis query execution failure."""
        logs_insights_client.client.start_query.return_value = None
        
        result = logs_insights_client.run_error_analysis(
            log_group_name="/aws/lambda/test",
            start_time=1000,
            end_time=2000
        )
        
        assert result is None

    def test_run_user_activity_query_success(self, logs_insights_client):
        """Test successful user activity query execution."""
        logs_insights_client.client.start_query.return_value = {"queryId": "query-456"}
        logs_insights_client.client.get_query_results.return_value = {
            "status": "Complete",
            "results": [
                [
                    {"field": "user_id", "value": "user-123"},
                    {"field": "action_count", "value": "10"}
                ]
            ],
            "statistics": {}
        }
        
        result = logs_insights_client.run_user_activity_query(
            log_group_name="/aws/lambda/test",
            start_time=1000,
            end_time=2000
        )
        
        assert result is not None
        assert result["status"] == "Complete"

    def test_run_user_activity_query_failure(self, logs_insights_client):
        """Test user activity query execution failure."""
        logs_insights_client.client.start_query.return_value = None
        
        result = logs_insights_client.run_user_activity_query(
            log_group_name="/aws/lambda/test",
            start_time=1000,
            end_time=2000
        )
        
        assert result is None

    def test_run_trade_execution_audit_success(self, logs_insights_client):
        """Test successful trade execution audit query execution."""
        logs_insights_client.client.start_query.return_value = {"queryId": "query-789"}
        logs_insights_client.client.get_query_results.return_value = {
            "status": "Complete",
            "results": [
                [
                    {"field": "status", "value": "completed"},
                    {"field": "trade_count", "value": "25"}
                ]
            ],
            "statistics": {}
        }
        
        result = logs_insights_client.run_trade_execution_audit(
            log_group_name="/aws/lambda/test",
            start_time=1000,
            end_time=2000
        )
        
        assert result is not None
        assert result["status"] == "Complete"

    def test_run_trade_execution_audit_failure(self, logs_insights_client):
        """Test trade execution audit query execution failure."""
        logs_insights_client.client.start_query.return_value = None
        
        result = logs_insights_client.run_trade_execution_audit(
            log_group_name="/aws/lambda/test",
            start_time=1000,
            end_time=2000
        )
        
        assert result is None


class TestFactoryFunction:
    """Tests for factory function."""

    def test_create_logs_insights_client(self):
        """Test factory function creates client correctly."""
        with patch("boto3.client"):
            client = create_logs_insights_client(region="eu-west-1")
            
            assert isinstance(client, CloudWatchLogsInsights)
            assert client.region == "eu-west-1"
