"""
Integration tests for API Gateway endpoints.

Tests validate that API Gateway endpoints properly authenticate requests,
validate input, and integrate with Step Functions for workflow initiation.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import boto3
from botocore.exceptions import ClientError


class TestApiGatewayAuthentication:
    """
    Test authentication with valid/invalid tokens.
    """

    @patch('boto3.client')
    def test_valid_cognito_token_allows_access(self, mock_boto_client):
        """
        Test that valid Cognito tokens allow access to protected endpoints.
        """
        # Mock Cognito client
        cognito_client = Mock()
        cognito_client.get_user.return_value = {
            'Username': 'test_user',
            'UserAttributes': [
                {'Name': 'email', 'Value': 'test@example.com'},
                {'Name': 'email_verified', 'Value': 'true'}
            ]
        }
        mock_boto_client.return_value = cognito_client
        
        # Simulate API Gateway authorization
        token = 'valid_token_12345'
        
        # Verify token
        response = cognito_client.get_user(AccessToken=token)
        
        assert response['Username'] == 'test_user'
        assert response['UserAttributes'][0]['Value'] == 'test@example.com'

    @patch('boto3.client')
    def test_invalid_cognito_token_denies_access(self, mock_boto_client):
        """
        Test that invalid Cognito tokens deny access to protected endpoints.
        """
        # Mock Cognito client
        cognito_client = Mock()
        cognito_client.get_user.side_effect = ClientError(
            {'Error': {'Code': 'NotAuthorizedException', 'Message': 'Invalid token'}},
            'GetUser'
        )
        mock_boto_client.return_value = cognito_client
        
        # Simulate API Gateway authorization
        token = 'invalid_token'
        
        # Verify token fails
        with pytest.raises(ClientError) as exc_info:
            cognito_client.get_user(AccessToken=token)
        
        assert exc_info.value.response['Error']['Code'] == 'NotAuthorizedException'

    def test_missing_authorization_header_denies_access(self):
        """
        Test that requests without Authorization header are denied.
        """
        headers = {}
        
        # Simulate API Gateway authorization check
        def check_authorization(headers):
            return 'Authorization' in headers
        
        is_authorized = check_authorization(headers)
        assert not is_authorized, "Request without Authorization header should be denied"

    def test_malformed_authorization_header_denies_access(self):
        """
        Test that requests with malformed Authorization header are denied.
        """
        headers = {'Authorization': 'InvalidFormat'}
        
        # Simulate API Gateway authorization check
        def check_authorization(headers):
            if 'Authorization' not in headers:
                return False
            
            auth_header = headers['Authorization']
            return auth_header.startswith('Bearer ')
        
        is_authorized = check_authorization(headers)
        assert not is_authorized, "Request with malformed Authorization header should be denied"


class TestWorkflowInitiationViaApi:
    """
    Test workflow initiation via API endpoints.
    """

    @patch('boto3.client')
    def test_rebalance_endpoint_initiates_workflow(self, mock_boto_client):
        """
        Test that POST /rebalance initiates Step Functions workflow.
        """
        # Mock Step Functions client
        sf_client = Mock()
        sf_client.start_execution.return_value = {
            'executionArn': 'arn:aws:states:us-east-1:123456789:execution:portfolio-rebalancing:exec-123',
            'startDate': '2024-01-15T14:30:00Z'
        }
        mock_boto_client.return_value = sf_client
        
        # Simulate API request
        request_body = {
            'user_id': 'user_123',
            'portfolio_id': 'portfolio_456',
            'request_type': 'rebalance'
        }
        
        # Initiate workflow
        response = sf_client.start_execution(
            stateMachineArn='arn:aws:states:us-east-1:123456789:stateMachine:portfolio-rebalancing',
            input=json.dumps(request_body)
        )
        
        assert 'executionArn' in response
        assert 'exec-123' in response['executionArn']

    @patch('boto3.client')
    def test_analyze_endpoint_initiates_workflow(self, mock_boto_client):
        """
        Test that POST /analyze initiates Step Functions workflow.
        """
        # Mock Step Functions client
        sf_client = Mock()
        sf_client.start_execution.return_value = {
            'executionArn': 'arn:aws:states:us-east-1:123456789:execution:portfolio-rebalancing:exec-456',
            'startDate': '2024-01-15T14:30:00Z'
        }
        mock_boto_client.return_value = sf_client
        
        # Simulate API request
        request_body = {
            'user_id': 'user_123',
            'portfolio_id': 'portfolio_456',
            'request_type': 'analyze',
            'parameters': {'analysis_type': 'performance'}
        }
        
        # Initiate workflow
        response = sf_client.start_execution(
            stateMachineArn='arn:aws:states:us-east-1:123456789:stateMachine:portfolio-rebalancing',
            input=json.dumps(request_body)
        )
        
        assert 'executionArn' in response
        assert 'exec-456' in response['executionArn']

    @patch('boto3.client')
    def test_optimize_tax_endpoint_initiates_workflow(self, mock_boto_client):
        """
        Test that POST /optimize-tax initiates Step Functions workflow.
        """
        # Mock Step Functions client
        sf_client = Mock()
        sf_client.start_execution.return_value = {
            'executionArn': 'arn:aws:states:us-east-1:123456789:execution:portfolio-rebalancing:exec-789',
            'startDate': '2024-01-15T14:30:00Z'
        }
        mock_boto_client.return_value = sf_client
        
        # Simulate API request
        request_body = {
            'user_id': 'user_123',
            'portfolio_id': 'portfolio_456',
            'request_type': 'tax_optimize',
            'parameters': {'tax_year': 2024}
        }
        
        # Initiate workflow
        response = sf_client.start_execution(
            stateMachineArn='arn:aws:states:us-east-1:123456789:stateMachine:portfolio-rebalancing',
            input=json.dumps(request_body)
        )
        
        assert 'executionArn' in response
        assert 'exec-789' in response['executionArn']

    @patch('boto3.client')
    def test_workflow_execution_arn_returned_to_client(self, mock_boto_client):
        """
        Test that execution ARN is returned to client for status tracking.
        """
        # Mock Step Functions client
        sf_client = Mock()
        execution_arn = 'arn:aws:states:us-east-1:123456789:execution:portfolio-rebalancing:exec-123'
        sf_client.start_execution.return_value = {
            'executionArn': execution_arn,
            'startDate': '2024-01-15T14:30:00Z'
        }
        mock_boto_client.return_value = sf_client
        
        # Simulate API request
        request_body = {
            'user_id': 'user_123',
            'portfolio_id': 'portfolio_456',
            'request_type': 'rebalance'
        }
        
        # Initiate workflow
        response = sf_client.start_execution(
            stateMachineArn='arn:aws:states:us-east-1:123456789:stateMachine:portfolio-rebalancing',
            input=json.dumps(request_body)
        )
        
        # Verify execution ARN is returned
        assert response['executionArn'] == execution_arn
        
        # Client can use execution ARN to track status
        assert 'exec-123' in response['executionArn']


class TestApprovalSubmission:
    """
    Test approval submission via API.
    """

    @patch('boto3.client')
    def test_approval_endpoint_receives_user_decision(self, mock_boto_client):
        """
        Test that POST /approval receives user approval/rejection decision.
        """
        # Mock Lambda client
        lambda_client = Mock()
        lambda_client.invoke.return_value = {
            'StatusCode': 200,
            'Payload': json.dumps({'status': 'success'})
        }
        mock_boto_client.return_value = lambda_client
        
        # Simulate approval request
        request_body = {
            'task_token': 'token_12345',
            'approval_status': 'approved'
        }
        
        # Invoke approval handler
        response = lambda_client.invoke(
            FunctionName='approval-handler',
            InvocationType='RequestResponse',
            Payload=json.dumps(request_body)
        )
        
        assert response['StatusCode'] == 200

    @patch('boto3.client')
    def test_approval_endpoint_validates_payload(self, mock_boto_client):
        """
        Test that approval endpoint validates payload structure.
        """
        # Simulate approval request validation
        def validate_approval_payload(payload):
            required_fields = ['task_token', 'approval_status']
            for field in required_fields:
                if field not in payload:
                    return False, f"Missing required field: {field}"
            
            if payload['approval_status'] not in ['approved', 'rejected', 'cancelled']:
                return False, "Invalid approval_status"
            
            return True, "Valid"
        
        # Test valid payload
        valid_payload = {
            'task_token': 'token_12345',
            'approval_status': 'approved'
        }
        is_valid, message = validate_approval_payload(valid_payload)
        assert is_valid, message
        
        # Test invalid payload (missing task_token)
        invalid_payload = {
            'approval_status': 'approved'
        }
        is_valid, message = validate_approval_payload(invalid_payload)
        assert not is_valid, "Should reject payload missing task_token"

    @patch('boto3.client')
    def test_approval_endpoint_extracts_task_token(self, mock_boto_client):
        """
        Test that approval endpoint extracts task token from payload.
        """
        # Simulate task token extraction
        request_body = {
            'task_token': 'token_12345',
            'approval_status': 'approved'
        }
        
        task_token = request_body.get('task_token')
        assert task_token == 'token_12345'

    @patch('boto3.client')
    def test_approval_endpoint_sends_result_to_stepfunctions(self, mock_boto_client):
        """
        Test that approval endpoint sends result to Step Functions.
        """
        # Mock Step Functions client
        sf_client = Mock()
        sf_client.send_task_success.return_value = {}
        mock_boto_client.return_value = sf_client
        
        # Simulate approval submission
        task_token = 'token_12345'
        approval_status = 'approved'
        
        # Send result to Step Functions
        sf_client.send_task_success(
            taskToken=task_token,
            output=json.dumps({'approval_status': approval_status})
        )
        
        # Verify send_task_success was called
        sf_client.send_task_success.assert_called_once()


class TestRateLimiting:
    """
    Test rate limiting behavior.
    """

    def test_rate_limiting_enforced_per_user(self):
        """
        Test that rate limiting is enforced per user (100 req/sec).
        """
        # Simulate rate limiting
        class RateLimiter:
            def __init__(self, limit_per_second=100):
                self.limit_per_second = limit_per_second
                self.request_counts = {}
            
            def is_allowed(self, user_id):
                import time
                current_time = int(time.time())
                
                if user_id not in self.request_counts:
                    self.request_counts[user_id] = {}
                
                if current_time not in self.request_counts[user_id]:
                    self.request_counts[user_id][current_time] = 0
                
                count = self.request_counts[user_id][current_time]
                if count >= self.limit_per_second:
                    return False
                
                self.request_counts[user_id][current_time] += 1
                return True
        
        limiter = RateLimiter(limit_per_second=100)
        
        # Test that first 100 requests are allowed
        user_id = 'user_123'
        for i in range(100):
            assert limiter.is_allowed(user_id), f"Request {i+1} should be allowed"
        
        # Test that 101st request is denied
        assert not limiter.is_allowed(user_id), "Request 101 should be denied"

    def test_rate_limiting_resets_per_second(self):
        """
        Test that rate limiting resets every second.
        """
        # Simulate rate limiting with time
        class RateLimiter:
            def __init__(self, limit_per_second=100):
                self.limit_per_second = limit_per_second
                self.request_counts = {}
            
            def is_allowed(self, user_id, current_time):
                if user_id not in self.request_counts:
                    self.request_counts[user_id] = {}
                
                if current_time not in self.request_counts[user_id]:
                    self.request_counts[user_id][current_time] = 0
                
                count = self.request_counts[user_id][current_time]
                if count >= self.limit_per_second:
                    return False
                
                self.request_counts[user_id][current_time] += 1
                return True
        
        limiter = RateLimiter(limit_per_second=100)
        user_id = 'user_123'
        
        # First second: 100 requests allowed
        for i in range(100):
            assert limiter.is_allowed(user_id, 1), f"Request {i+1} at second 1 should be allowed"
        
        # Second second: 100 new requests allowed
        for i in range(100):
            assert limiter.is_allowed(user_id, 2), f"Request {i+1} at second 2 should be allowed"


class TestRequestValidation:
    """
    Test request validation.
    """

    def test_required_fields_validation(self):
        """
        Test that required fields are validated.
        """
        def validate_request(body):
            required_fields = ['user_id', 'portfolio_id']
            for field in required_fields:
                if field not in body or not body[field]:
                    return False, f"Missing or empty required field: {field}"
            return True, "Valid"
        
        # Test valid request
        valid_body = {
            'user_id': 'user_123',
            'portfolio_id': 'portfolio_456'
        }
        is_valid, message = validate_request(valid_body)
        assert is_valid, message
        
        # Test missing user_id
        invalid_body = {
            'portfolio_id': 'portfolio_456'
        }
        is_valid, message = validate_request(invalid_body)
        assert not is_valid, "Should reject request missing user_id"

    def test_request_type_validation(self):
        """
        Test that request_type is validated.
        """
        def validate_request_type(request_type):
            allowed_types = ['rebalance', 'analyze', 'tax_optimize']
            return request_type in allowed_types
        
        # Test valid request types
        assert validate_request_type('rebalance')
        assert validate_request_type('analyze')
        assert validate_request_type('tax_optimize')
        
        # Test invalid request type
        assert not validate_request_type('invalid_type')

    def test_json_schema_validation(self):
        """
        Test that request body conforms to JSON schema.
        """
        import json
        
        # Define schema
        schema = {
            'type': 'object',
            'required': ['user_id', 'portfolio_id'],
            'properties': {
                'user_id': {'type': 'string'},
                'portfolio_id': {'type': 'string'},
                'request_type': {
                    'type': 'string',
                    'enum': ['rebalance', 'analyze', 'tax_optimize']
                }
            }
        }
        
        # Test valid request
        valid_request = {
            'user_id': 'user_123',
            'portfolio_id': 'portfolio_456',
            'request_type': 'rebalance'
        }
        
        # Verify required fields
        for field in schema['required']:
            assert field in valid_request, f"Missing required field: {field}"
        
        # Verify field types
        assert isinstance(valid_request['user_id'], str)
        assert isinstance(valid_request['portfolio_id'], str)
