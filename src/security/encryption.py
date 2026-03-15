"""Data encryption verification and configuration."""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class EncryptionStatus(Enum):
    """Encryption status enumeration."""
    ENCRYPTED = "encrypted"
    NOT_ENCRYPTED = "not_encrypted"
    UNKNOWN = "unknown"
    ERROR = "error"


@dataclass
class EncryptionCheckResult:
    """Result of encryption verification check."""
    resource_name: str
    resource_type: str
    status: EncryptionStatus
    encryption_type: Optional[str] = None
    kms_key_id: Optional[str] = None
    error: Optional[str] = None
    
    def is_encrypted(self) -> bool:
        """Check if resource is encrypted."""
        return self.status == EncryptionStatus.ENCRYPTED


def verify_dynamodb_encryption(table_name: str) -> EncryptionCheckResult:
    """
    Verify that a DynamoDB table uses KMS encryption.
    
    Args:
        table_name: Name of the DynamoDB table
        
    Returns:
        EncryptionCheckResult with encryption status
    """
    try:
        dynamodb = boto3.client('dynamodb')
        
        # Describe table
        response = dynamodb.describe_table(TableName=table_name)
        table = response['Table']
        
        # Check SSE specification
        sse_spec = table.get('SSEDescription', {})
        
        if not sse_spec:
            return EncryptionCheckResult(
                resource_name=table_name,
                resource_type='dynamodb_table',
                status=EncryptionStatus.NOT_ENCRYPTED,
                error='No SSE specification found'
            )
        
        sse_type = sse_spec.get('SSEType', 'UNKNOWN')
        status = sse_spec.get('Status', 'UNKNOWN')
        
        if status != 'ENABLED':
            return EncryptionCheckResult(
                resource_name=table_name,
                resource_type='dynamodb_table',
                status=EncryptionStatus.NOT_ENCRYPTED,
                error=f'SSE status is {status}, not ENABLED'
            )
        
        if sse_type != 'KMS':
            return EncryptionCheckResult(
                resource_name=table_name,
                resource_type='dynamodb_table',
                status=EncryptionStatus.NOT_ENCRYPTED,
                encryption_type=sse_type,
                error=f'SSE type is {sse_type}, not KMS'
            )
        
        kms_key_arn = sse_spec.get('KMSMasterKeyArn')
        
        return EncryptionCheckResult(
            resource_name=table_name,
            resource_type='dynamodb_table',
            status=EncryptionStatus.ENCRYPTED,
            encryption_type='KMS',
            kms_key_id=kms_key_arn
        )
    
    except ClientError as e:
        logger.error(f"Error verifying DynamoDB encryption for {table_name}: {e}")
        return EncryptionCheckResult(
            resource_name=table_name,
            resource_type='dynamodb_table',
            status=EncryptionStatus.ERROR,
            error=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error verifying DynamoDB encryption: {e}")
        return EncryptionCheckResult(
            resource_name=table_name,
            resource_type='dynamodb_table',
            status=EncryptionStatus.ERROR,
            error=str(e)
        )


def verify_s3_encryption(bucket_name: str) -> EncryptionCheckResult:
    """
    Verify that an S3 bucket uses SSE-KMS encryption.
    
    Args:
        bucket_name: Name of the S3 bucket
        
    Returns:
        EncryptionCheckResult with encryption status
    """
    try:
        s3 = boto3.client('s3')
        
        # Get bucket encryption
        try:
            response = s3.get_bucket_encryption(Bucket=bucket_name)
            rules = response.get('ServerSideEncryptionConfiguration', {}).get('Rules', [])
            
            if not rules:
                return EncryptionCheckResult(
                    resource_name=bucket_name,
                    resource_type='s3_bucket',
                    status=EncryptionStatus.NOT_ENCRYPTED,
                    error='No encryption rules found'
                )
            
            # Check first rule (typically only one)
            rule = rules[0]
            sse_algorithm = rule.get('ApplyServerSideEncryptionByDefault', {}).get('SSEAlgorithm')
            
            if sse_algorithm != 'aws:kms':
                return EncryptionCheckResult(
                    resource_name=bucket_name,
                    resource_type='s3_bucket',
                    status=EncryptionStatus.NOT_ENCRYPTED,
                    encryption_type=sse_algorithm,
                    error=f'SSE algorithm is {sse_algorithm}, not aws:kms'
                )
            
            kms_key_id = rule.get('ApplyServerSideEncryptionByDefault', {}).get('KMSMasterKeyID')
            
            return EncryptionCheckResult(
                resource_name=bucket_name,
                resource_type='s3_bucket',
                status=EncryptionStatus.ENCRYPTED,
                encryption_type='aws:kms',
                kms_key_id=kms_key_id
            )
        
        except s3.exceptions.ServerSideEncryptionConfigurationNotFoundError:
            return EncryptionCheckResult(
                resource_name=bucket_name,
                resource_type='s3_bucket',
                status=EncryptionStatus.NOT_ENCRYPTED,
                error='No encryption configuration found'
            )
    
    except ClientError as e:
        logger.error(f"Error verifying S3 encryption for {bucket_name}: {e}")
        return EncryptionCheckResult(
            resource_name=bucket_name,
            resource_type='s3_bucket',
            status=EncryptionStatus.ERROR,
            error=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error verifying S3 encryption: {e}")
        return EncryptionCheckResult(
            resource_name=bucket_name,
            resource_type='s3_bucket',
            status=EncryptionStatus.ERROR,
            error=str(e)
        )


def verify_opensearch_encryption(collection_name: str) -> EncryptionCheckResult:
    """
    Verify that an OpenSearch Serverless collection uses encryption.
    
    Args:
        collection_name: Name of the OpenSearch collection
        
    Returns:
        EncryptionCheckResult with encryption status
    """
    try:
        aoss = boto3.client('opensearchserverless')
        
        # List collections to find the one we're looking for
        response = aoss.list_collections()
        collections = response.get('collectionSummaries', [])
        
        target_collection = None
        for collection in collections:
            if collection.get('name') == collection_name:
                target_collection = collection
                break
        
        if not target_collection:
            return EncryptionCheckResult(
                resource_name=collection_name,
                resource_type='opensearch_collection',
                status=EncryptionStatus.UNKNOWN,
                error=f'Collection {collection_name} not found'
            )
        
        # OpenSearch Serverless collections are encrypted by default with AWS-owned keys
        # Check if encryption policy exists
        try:
            policies_response = aoss.list_security_policies(type='encryption')
            policies = policies_response.get('securityPolicySummaries', [])
            
            # Look for encryption policy for this collection
            encryption_enabled = False
            for policy in policies:
                if collection_name in policy.get('name', ''):
                    encryption_enabled = True
                    break
            
            # OpenSearch Serverless always encrypts data at rest
            # If no custom policy, AWS-owned keys are used
            if not encryption_enabled:
                # Default encryption with AWS-owned keys
                return EncryptionCheckResult(
                    resource_name=collection_name,
                    resource_type='opensearch_collection',
                    status=EncryptionStatus.ENCRYPTED,
                    encryption_type='AWS-owned-keys',
                    error=None
                )
            
            return EncryptionCheckResult(
                resource_name=collection_name,
                resource_type='opensearch_collection',
                status=EncryptionStatus.ENCRYPTED,
                encryption_type='customer-managed-keys'
            )
        
        except Exception as e:
            # If we can't check policies, assume default encryption
            logger.warning(f"Could not verify encryption policy for {collection_name}: {e}")
            return EncryptionCheckResult(
                resource_name=collection_name,
                resource_type='opensearch_collection',
                status=EncryptionStatus.ENCRYPTED,
                encryption_type='AWS-owned-keys'
            )
    
    except ClientError as e:
        logger.error(f"Error verifying OpenSearch encryption for {collection_name}: {e}")
        return EncryptionCheckResult(
            resource_name=collection_name,
            resource_type='opensearch_collection',
            status=EncryptionStatus.ERROR,
            error=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error verifying OpenSearch encryption: {e}")
        return EncryptionCheckResult(
            resource_name=collection_name,
            resource_type='opensearch_collection',
            status=EncryptionStatus.ERROR,
            error=str(e)
        )


def verify_all_encryption(
    dynamodb_tables: list,
    s3_buckets: list,
    opensearch_collections: list
) -> Dict[str, Any]:
    """
    Verify encryption for all resources.
    
    Args:
        dynamodb_tables: List of DynamoDB table names
        s3_buckets: List of S3 bucket names
        opensearch_collections: List of OpenSearch collection names
        
    Returns:
        Dictionary with encryption verification results
    """
    results = {
        'dynamodb': [],
        's3': [],
        'opensearch': [],
        'all_encrypted': True
    }
    
    # Check DynamoDB tables
    for table_name in dynamodb_tables:
        result = verify_dynamodb_encryption(table_name)
        results['dynamodb'].append(result)
        if not result.is_encrypted():
            results['all_encrypted'] = False
    
    # Check S3 buckets
    for bucket_name in s3_buckets:
        result = verify_s3_encryption(bucket_name)
        results['s3'].append(result)
        if not result.is_encrypted():
            results['all_encrypted'] = False
    
    # Check OpenSearch collections
    for collection_name in opensearch_collections:
        result = verify_opensearch_encryption(collection_name)
        results['opensearch'].append(result)
        if not result.is_encrypted():
            results['all_encrypted'] = False
    
    return results
