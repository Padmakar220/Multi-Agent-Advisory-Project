"""Unit tests for security controls."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

from src.security.encryption import (
    verify_dynamodb_encryption,
    verify_s3_encryption,
    verify_opensearch_encryption,
    EncryptionStatus
)
from src.security.authorization import (
    check_user_access,
    enforce_user_isolation,
    AuthorizationChecker
)
from src.security.audit_logging import (
    log_agent_action,
    log_data_access,
    AuditLogger
)
from src.security.tls_config import (
    verify_tls_version,
    TLSVersion
)


class TestDynamoDBEncryption:
    """Test DynamoDB encryption verification."""
    
    def test_dynamodb_encrypted_with_kms(self):
        """Test DynamoDB table with KMS encryption."""
        with patch('boto3.client') as mock_boto:
            mock_dynamodb = MagicMock()
            mock_boto.return_value = mock_dynamodb
            
            mock_dynamodb.describe_table.return_value = {
                'Table': {
                    'TableName': 'test-table',
                    'SSEDescription': {
                        'Status': 'ENABLED',
                        'SSEType': 'KMS',
                        'KMSMasterKeyArn': 'arn:aws:kms:us-east-1:123456789:key/12345'
                    }
                }
            }
            
            result = verify_dynamodb_encryption('test-table')
            
            assert result.is_encrypted()
            assert result.status == EncryptionStatus.ENCRYPTED
            assert result.encryption_type == 'KMS'
    
    def test_dynamodb_not_encrypted(self):
        """Test DynamoDB table without encryption."""
        with patch('boto3.client') as mock_boto:
            mock_dynamodb = MagicMock()
            mock_boto.return_value = mock_dynamodb
            
            mock_dynamodb.describe_table.return_value = {
                'Table': {
                    'TableName': 'test-table',
                    'SSEDescription': {}
                }
            }
            
            result = verify_dynamodb_encryption('test-table')
            
            assert not result.is_encrypted()
            assert result.status == EncryptionStatus.NOT_ENCRYPTED


class TestS3Encryption:
    """Test S3 encryption verification."""
    
    def test_s3_encrypted_with_kms(self):
        """Test S3 bucket with KMS encryption."""
        with patch('boto3.client') as mock_boto:
            mock_s3 = MagicMock()
            mock_boto.return_value = mock_s3
            
            mock_s3.get_bucket_encryption.return_value = {
                'ServerSideEncryptionConfiguration': {
                    'Rules': [
                        {
                            'ApplyServerSideEncryptionByDefault': {
                                'SSEAlgorithm': 'aws:kms',
                                'KMSMasterKeyID': 'arn:aws:kms:us-east-1:123456789:key/12345'
                            }
                        }
                    ]
                }
            }
            
            result = verify_s3_encryption('test-bucket')
            
            assert result.is_encrypted()
            assert result.status == EncryptionStatus.ENCRYPTED
            assert result.encryption_type == 'aws:kms'
    
    def test_s3_not_encrypted(self):
        """Test S3 bucket without encryption."""
        with patch('boto3.client') as mock_boto:
            mock_s3 = MagicMock()
            mock_boto.return_value = mock_s3
            
            mock_s3.get_bucket_encryption.side_effect = \
                mock_s3.exceptions.ServerSideEncryptionConfigurationNotFoundError()
            
            result = verify_s3_encryption('test-bucket')
            
            assert not result.is_encrypted()
            assert result.status == EncryptionStatus.NOT_ENCRYPTED


class TestUserIsolation:
    """Test user data isolation."""
    
    def test_user_can_access_own_resource(self):
        """Test that user can access their own resource."""
        result = enforce_user_isolation(
            user_id='user-123',
            resource_owner='user-123',
            resource_type='portfolio',
            resource_id='portfolio-456'
        )
        
        assert result is True
    
    def test_user_cannot_access_other_resource(self):
        """Test that user cannot access other user's resource."""
        result = enforce_user_isolation(
            user_id='user-123',
            resource_owner='user-456',
            resource_type='portfolio',
            resource_id='portfolio-789'
        )
        
        assert result is False


class TestAuthorization:
    """Test authorization checks."""
    
    def test_authorization_with_owner(self):
        """Test authorization when user owns resource."""
        result = check_user_access(
            user_id='user-123',
            resource_type='portfolio',
            resource_id='portfolio-456',
            action='read',
            resource_owner='user-123'
        )
        
        assert result.user_id == 'user-123'
        assert result.resource_id == 'portfolio-456'
    
    def test_authorization_without_owner(self):
        """Test authorization when user doesn't own resource."""
        result = check_user_access(
            user_id='user-123',
            resource_type='portfolio',
            resource_id='portfolio-456',
            action='read',
            resource_owner='user-456'
        )
        
        assert result.authorized is False


class TestAuditLogging:
    """Test audit logging."""
    
    def test_log_agent_action(self):
        """Test logging agent action."""
        with patch('src.security.audit_logging.logger') as mock_logger:
            trace_id = log_agent_action(
                user_id='user-123',
                agent_type='portfolio_analyzer',
                action_type='read',
                resource_type='portfolio',
                resource_id='portfolio-456'
            )
            
            assert trace_id is not None
            assert len(trace_id) > 0
            mock_logger.info.assert_called()
    
    def test_log_data_access(self):
        """Test logging data access."""
        with patch('src.security.audit_logging.logger') as mock_logger:
            trace_id = log_data_access(
                user_id='user-123',
                agent_type='portfolio_analyzer',
                access_type='read',
                resource_type='portfolio',
                resource_id='portfolio-456'
            )
            
            assert trace_id is not None
            assert len(trace_id) > 0
            mock_logger.info.assert_called()


class TestTLSConfiguration:
    """Test TLS configuration."""
    
    def test_api_gateway_tls_check(self):
        """Test API Gateway TLS version check."""
        with patch('boto3.client') as mock_boto:
            mock_apigateway = MagicMock()
            mock_boto.return_value = mock_apigateway
            
            mock_apigateway.get_rest_apis.return_value = {
                'items': [
                    {
                        'id': 'api123',
                        'name': 'test-api'
                    }
                ]
            }
            
            mock_apigateway.get_stages.return_value = {
                'item': [
                    {
                        'stageName': 'prod'
                    }
                ]
            }
            
            result = verify_tls_version(
                'test-api',
                'api_gateway',
                TLSVersion.TLS_1_3
            )
            
            assert result.resource_name == 'test-api'
            assert result.resource_type == 'api_gateway'
            assert result.min_tls_version is not None
