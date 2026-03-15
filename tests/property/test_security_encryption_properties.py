"""
Property-based tests for data encryption at rest.

Tests validate that all portfolio data is encrypted using AWS KMS.
"""

import pytest
from hypothesis import given, settings, strategies as st
from unittest.mock import Mock, patch, MagicMock
import boto3
from botocore.exceptions import ClientError

from src.security.encryption import (
    verify_dynamodb_encryption,
    verify_s3_encryption,
    verify_opensearch_encryption,
    EncryptionStatus
)


class TestDataEncryptionAtRest:
    """
    Property 35: Data Encryption at Rest
    
    For any portfolio data stored in DynamoDB, the data should be encrypted 
    using AWS KMS with a customer-managed key.
    
    Validates: Requirements 8.5
    """

    @settings(max_examples=50)
    @given(
        table_name=st.text(min_size=1, max_size=100),
        sse_enabled=st.booleans(),
        sse_type=st.sampled_from(['KMS', 'AES256', None])
    )
    def test_dynamodb_kms_encryption(self, table_name, sse_enabled, sse_type):
        """
        Test that DynamoDB tables use KMS encryption.
        
        For any DynamoDB table, SSE should be enabled with KMS type.
        """
        with patch('boto3.client') as mock_boto:
            mock_dynamodb = MagicMock()
            mock_boto.return_value = mock_dynamodb
            
            if sse_enabled and sse_type == 'KMS':
                mock_dynamodb.describe_table.return_value = {
                    'Table': {
                        'TableName': table_name,
                        'SSEDescription': {
                            'Status': 'ENABLED',
                            'SSEType': 'KMS',
                            'KMSMasterKeyArn': 'arn:aws:kms:us-east-1:123456789:key/12345'
                        }
                    }
                }
                
                result = verify_dynamodb_encryption(table_name)
                
                assert result.is_encrypted(), "DynamoDB table should be encrypted with KMS"
                assert result.status == EncryptionStatus.ENCRYPTED
                assert result.encryption_type == 'KMS'
            
            elif sse_enabled and sse_type != 'KMS':
                mock_dynamodb.describe_table.return_value = {
                    'Table': {
                        'TableName': table_name,
                        'SSEDescription': {
                            'Status': 'ENABLED',
                            'SSEType': sse_type or 'AES256'
                        }
                    }
                }
                
                result = verify_dynamodb_encryption(table_name)
                
                assert not result.is_encrypted(), f"DynamoDB should not be encrypted with {sse_type}"
                assert result.status == EncryptionStatus.NOT_ENCRYPTED
            
            else:
                mock_dynamodb.describe_table.return_value = {
                    'Table': {
                        'TableName': table_name,
                        'SSEDescription': {} if sse_enabled else None
                    }
                }
                
                result = verify_dynamodb_encryption(table_name)
                
                assert not result.is_encrypted(), "DynamoDB should not be encrypted"
                assert result.status == EncryptionStatus.NOT_ENCRYPTED

    @settings(max_examples=50)
    @given(
        bucket_name=st.text(min_size=1, max_size=100),
        has_encryption=st.booleans(),
        encryption_type=st.sampled_from(['aws:kms', 'AES256', None])
    )
    def test_s3_kms_encryption(self, bucket_name, has_encryption, encryption_type):
        """
        Test that S3 buckets use SSE-KMS encryption.
        
        For any S3 bucket, encryption should be enabled with aws:kms type.
        """
        with patch('boto3.client') as mock_boto:
            mock_s3 = MagicMock()
            mock_boto.return_value = mock_s3
            
            if has_encryption and encryption_type == 'aws:kms':
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
                
                result = verify_s3_encryption(bucket_name)
                
                assert result.is_encrypted(), "S3 bucket should be encrypted with KMS"
                assert result.status == EncryptionStatus.ENCRYPTED
                assert result.encryption_type == 'aws:kms'
            
            elif has_encryption and encryption_type != 'aws:kms':
                mock_s3.get_bucket_encryption.return_value = {
                    'ServerSideEncryptionConfiguration': {
                        'Rules': [
                            {
                                'ApplyServerSideEncryptionByDefault': {
                                    'SSEAlgorithm': encryption_type or 'AES256'
                                }
                            }
                        ]
                    }
                }
                
                result = verify_s3_encryption(bucket_name)
                
                assert not result.is_encrypted(), f"S3 should not be encrypted with {encryption_type}"
                assert result.status == EncryptionStatus.NOT_ENCRYPTED
            
            else:
                mock_s3.get_bucket_encryption.side_effect = \
                    mock_s3.exceptions.ServerSideEncryptionConfigurationNotFoundError()
                
                result = verify_s3_encryption(bucket_name)
                
                assert not result.is_encrypted(), "S3 should not be encrypted"
                assert result.status == EncryptionStatus.NOT_ENCRYPTED

    @settings(max_examples=50)
    @given(
        collection_name=st.text(min_size=1, max_size=100)
    )
    def test_opensearch_encryption(self, collection_name):
        """
        Test that OpenSearch collections use encryption.
        
        For any OpenSearch collection, encryption should be enabled.
        """
        with patch('boto3.client') as mock_boto:
            mock_aoss = MagicMock()
            mock_boto.return_value = mock_aoss
            
            mock_aoss.list_collections.return_value = {
                'collectionSummaries': [
                    {
                        'name': collection_name,
                        'arn': f'arn:aws:aoss:us-east-1:123456789:collection/{collection_name}'
                    }
                ]
            }
            
            mock_aoss.list_security_policies.return_value = {
                'securityPolicySummaries': []
            }
            
            result = verify_opensearch_encryption(collection_name)
            
            # OpenSearch Serverless is encrypted by default
            assert result.is_encrypted(), "OpenSearch collection should be encrypted"
            assert result.status == EncryptionStatus.ENCRYPTED

    @settings(max_examples=50)
    @given(
        table_name=st.text(min_size=1, max_size=100)
    )
    def test_dynamodb_encryption_error_handling(self, table_name):
        """
        Test error handling for DynamoDB encryption checks.
        
        For any error during encryption verification, the result should
        indicate an error status.
        """
        with patch('boto3.client') as mock_boto:
            mock_dynamodb = MagicMock()
            mock_boto.return_value = mock_dynamodb
            
            mock_dynamodb.describe_table.side_effect = ClientError(
                {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Table not found'}},
                'DescribeTable'
            )
            
            result = verify_dynamodb_encryption(table_name)
            
            assert result.status == EncryptionStatus.ERROR
            assert result.error is not None

    @settings(max_examples=50)
    @given(
        bucket_name=st.text(min_size=1, max_size=100)
    )
    def test_s3_encryption_error_handling(self, bucket_name):
        """
        Test error handling for S3 encryption checks.
        
        For any error during encryption verification, the result should
        indicate an error status.
        """
        with patch('boto3.client') as mock_boto:
            mock_s3 = MagicMock()
            mock_boto.return_value = mock_s3
            
            mock_s3.get_bucket_encryption.side_effect = ClientError(
                {'Error': {'Code': 'NoSuchBucket', 'Message': 'Bucket not found'}},
                'GetBucketEncryption'
            )
            
            result = verify_s3_encryption(bucket_name)
            
            assert result.status == EncryptionStatus.ERROR
            assert result.error is not None

    @settings(max_examples=50)
    @given(
        kms_key_id=st.text(min_size=10, max_size=200)
    )
    def test_kms_key_id_extraction(self, kms_key_id):
        """
        Test that KMS key IDs are properly extracted.
        
        For any encrypted resource, the KMS key ID should be captured.
        """
        with patch('boto3.client') as mock_boto:
            mock_dynamodb = MagicMock()
            mock_boto.return_value = mock_dynamodb
            
            mock_dynamodb.describe_table.return_value = {
                'Table': {
                    'TableName': 'test-table',
                    'SSEDescription': {
                        'Status': 'ENABLED',
                        'SSEType': 'KMS',
                        'KMSMasterKeyArn': kms_key_id
                    }
                }
            }
            
            result = verify_dynamodb_encryption('test-table')
            
            assert result.kms_key_id == kms_key_id
            assert result.is_encrypted()
