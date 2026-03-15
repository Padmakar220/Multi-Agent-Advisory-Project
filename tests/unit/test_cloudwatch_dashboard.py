"""Unit tests for CloudWatch Dashboard management."""

import json
import pytest
from unittest.mock import MagicMock, patch, call
from src.utils.cloudwatch_dashboard import CloudWatchDashboard, create_dashboard_manager


@pytest.fixture
def dashboard_manager():
    """Create a dashboard manager with mocked boto3 client."""
    with patch("boto3.client") as mock_client:
        manager = CloudWatchDashboard(region="us-east-1")
        manager.client = MagicMock()
        yield manager


class TestCloudWatchDashboard:
    """Tests for CloudWatchDashboard class."""

    def test_init(self):
        """Test dashboard manager initialization."""
        with patch("boto3.client"):
            manager = CloudWatchDashboard(region="us-west-2")
            assert manager.region == "us-west-2"
            assert manager.namespace == "MultiAgentAdvisorySystem"

    def test_create_dashboard_success(self, dashboard_manager):
        """Test successful dashboard creation."""
        dashboard_body = {"widgets": []}
        dashboard_manager.client.put_dashboard.return_value = {}
        
        result = dashboard_manager.create_dashboard("TestDashboard", dashboard_body)
        
        assert result is True
        dashboard_manager.client.put_dashboard.assert_called_once()
        call_args = dashboard_manager.client.put_dashboard.call_args
        assert call_args[1]["DashboardName"] == "TestDashboard"
        assert json.loads(call_args[1]["DashboardBody"]) == dashboard_body

    def test_create_dashboard_failure(self, dashboard_manager):
        """Test dashboard creation failure."""
        dashboard_manager.client.put_dashboard.side_effect = Exception("API Error")
        
        result = dashboard_manager.create_dashboard("TestDashboard", {})
        
        assert result is False

    def test_delete_dashboard_success(self, dashboard_manager):
        """Test successful dashboard deletion."""
        dashboard_manager.client.delete_dashboards.return_value = {}
        
        result = dashboard_manager.delete_dashboard("TestDashboard")
        
        assert result is True
        dashboard_manager.client.delete_dashboards.assert_called_once_with(
            DashboardNames=["TestDashboard"]
        )

    def test_delete_dashboard_failure(self, dashboard_manager):
        """Test dashboard deletion failure."""
        dashboard_manager.client.delete_dashboards.side_effect = Exception("API Error")
        
        result = dashboard_manager.delete_dashboard("TestDashboard")
        
        assert result is False

    def test_get_dashboard_success(self, dashboard_manager):
        """Test successful dashboard retrieval."""
        dashboard_body = {"widgets": [{"type": "metric"}]}
        dashboard_manager.client.get_dashboard.return_value = {
            "DashboardBody": json.dumps(dashboard_body)
        }
        
        result = dashboard_manager.get_dashboard("TestDashboard")
        
        assert result == dashboard_body

    def test_get_dashboard_not_found(self, dashboard_manager):
        """Test dashboard retrieval when not found."""
        from botocore.exceptions import ClientError
        error = ClientError(
            {"Error": {"Code": "InvalidParameterInput"}},
            "GetDashboard"
        )
        dashboard_manager.client.get_dashboard.side_effect = error
        
        result = dashboard_manager.get_dashboard("NonExistent")
        
        assert result is None

    def test_get_dashboard_error(self, dashboard_manager):
        """Test dashboard retrieval with error."""
        from botocore.exceptions import ClientError
        error = ClientError(
            {"Error": {"Code": "InternalFailure"}},
            "GetDashboard"
        )
        dashboard_manager.client.get_dashboard.side_effect = error
        
        result = dashboard_manager.get_dashboard("TestDashboard")
        
        assert result is None

    def test_list_dashboards_success(self, dashboard_manager):
        """Test successful dashboard listing."""
        dashboard_manager.client.list_dashboards.return_value = {
            "DashboardEntries": [
                {"DashboardName": "Dashboard1"},
                {"DashboardName": "Dashboard2"},
            ]
        }
        
        result = dashboard_manager.list_dashboards()
        
        assert result == ["Dashboard1", "Dashboard2"]

    def test_list_dashboards_empty(self, dashboard_manager):
        """Test dashboard listing when empty."""
        dashboard_manager.client.list_dashboards.return_value = {"DashboardEntries": []}
        
        result = dashboard_manager.list_dashboards()
        
        assert result == []

    def test_list_dashboards_error(self, dashboard_manager):
        """Test dashboard listing with error."""
        dashboard_manager.client.list_dashboards.side_effect = Exception("API Error")
        
        result = dashboard_manager.list_dashboards()
        
        assert result == []

    def test_create_monitoring_dashboard(self, dashboard_manager):
        """Test creation of main monitoring dashboard."""
        dashboard_manager.client.put_dashboard.return_value = {}
        
        result = dashboard_manager.create_monitoring_dashboard()
        
        assert result is True
        dashboard_manager.client.put_dashboard.assert_called_once()
        call_args = dashboard_manager.client.put_dashboard.call_args
        assert call_args[1]["DashboardName"] == "MultiAgentAdvisoryMonitoring"
        
        body = json.loads(call_args[1]["DashboardBody"])
        assert "widgets" in body
        assert len(body["widgets"]) == 4

    def test_lambda_performance_widget(self, dashboard_manager):
        """Test Lambda performance widget creation."""
        widget = dashboard_manager._create_lambda_performance_widget()
        
        assert widget["type"] == "metric"
        assert widget["properties"]["title"] == "Lambda Performance Metrics"
        assert len(widget["properties"]["metrics"]) == 6
        assert widget["properties"]["region"] == "us-east-1"

    def test_agent_performance_widget(self, dashboard_manager):
        """Test agent performance widget creation."""
        widget = dashboard_manager._create_agent_performance_widget()
        
        assert widget["type"] == "metric"
        assert widget["properties"]["title"] == "Agent Performance Metrics"
        assert len(widget["properties"]["metrics"]) == 6
        assert widget["properties"]["region"] == "us-east-1"

    def test_error_logs_widget(self, dashboard_manager):
        """Test error logs widget creation."""
        widget = dashboard_manager._create_error_logs_widget()
        
        assert widget["type"] == "log"
        assert widget["properties"]["title"] == "Recent Errors by Service and Type"
        assert "ERROR" in widget["properties"]["query"]
        assert "CRITICAL" in widget["properties"]["query"]

    def test_dynamodb_metrics_widget(self, dashboard_manager):
        """Test DynamoDB metrics widget creation."""
        widget = dashboard_manager._create_dynamodb_metrics_widget()
        
        assert widget["type"] == "metric"
        assert widget["properties"]["title"] == "DynamoDB Metrics"
        assert len(widget["properties"]["metrics"]) == 6
        assert widget["properties"]["region"] == "us-east-1"

    def test_add_widget_success(self, dashboard_manager):
        """Test adding a widget to existing dashboard."""
        existing_dashboard = {"widgets": [{"type": "metric"}]}
        dashboard_manager.client.get_dashboard.return_value = {
            "DashboardBody": json.dumps(existing_dashboard)
        }
        dashboard_manager.client.put_dashboard.return_value = {}
        
        new_widget = {"type": "log"}
        result = dashboard_manager.add_widget("TestDashboard", new_widget)
        
        assert result is True
        dashboard_manager.client.put_dashboard.assert_called_once()
        call_args = dashboard_manager.client.put_dashboard.call_args
        body = json.loads(call_args[1]["DashboardBody"])
        assert len(body["widgets"]) == 2
        assert body["widgets"][1] == new_widget

    def test_add_widget_dashboard_not_found(self, dashboard_manager):
        """Test adding widget when dashboard doesn't exist."""
        from botocore.exceptions import ClientError
        error = ClientError(
            {"Error": {"Code": "InvalidParameterInput"}},
            "GetDashboard"
        )
        dashboard_manager.client.get_dashboard.side_effect = error
        
        result = dashboard_manager.add_widget("NonExistent", {})
        
        assert result is False

    def test_remove_widget_success(self, dashboard_manager):
        """Test removing a widget from dashboard."""
        existing_dashboard = {
            "widgets": [
                {"type": "metric"},
                {"type": "log"},
                {"type": "metric"}
            ]
        }
        dashboard_manager.client.get_dashboard.return_value = {
            "DashboardBody": json.dumps(existing_dashboard)
        }
        dashboard_manager.client.put_dashboard.return_value = {}
        
        result = dashboard_manager.remove_widget("TestDashboard", 1)
        
        assert result is True
        dashboard_manager.client.put_dashboard.assert_called_once()
        call_args = dashboard_manager.client.put_dashboard.call_args
        body = json.loads(call_args[1]["DashboardBody"])
        assert len(body["widgets"]) == 2
        assert body["widgets"][0]["type"] == "metric"
        assert body["widgets"][1]["type"] == "metric"

    def test_remove_widget_invalid_index(self, dashboard_manager):
        """Test removing widget with invalid index."""
        existing_dashboard = {"widgets": [{"type": "metric"}]}
        dashboard_manager.client.get_dashboard.return_value = {
            "DashboardBody": json.dumps(existing_dashboard)
        }
        
        result = dashboard_manager.remove_widget("TestDashboard", 5)
        
        assert result is False

    def test_remove_widget_dashboard_not_found(self, dashboard_manager):
        """Test removing widget when dashboard doesn't exist."""
        from botocore.exceptions import ClientError
        error = ClientError(
            {"Error": {"Code": "InvalidParameterInput"}},
            "GetDashboard"
        )
        dashboard_manager.client.get_dashboard.side_effect = error
        
        result = dashboard_manager.remove_widget("NonExistent", 0)
        
        assert result is False


class TestFactoryFunction:
    """Tests for factory function."""

    def test_create_dashboard_manager(self):
        """Test factory function creates manager correctly."""
        with patch("boto3.client"):
            manager = create_dashboard_manager(region="eu-west-1")
            
            assert isinstance(manager, CloudWatchDashboard)
            assert manager.region == "eu-west-1"
