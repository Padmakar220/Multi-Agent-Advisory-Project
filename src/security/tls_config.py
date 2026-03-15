"""TLS configuration and verification."""

import logging
from typing import Optional
from enum import Enum
from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class TLSVersion(Enum):
    """TLS version enumeration."""
    TLS_1_0 = "TLSv1"
    TLS_1_1 = "TLSv1.1"
    TLS_1_2 = "TLSv1.2"
    TLS_1_3 = "TLSv1.3"


@dataclass
class TLSCheckResult:
    """Result of TLS version check."""
    resource_name: str
    resource_type: str
    min_tls_version: Optional[TLSVersion]
    is_compliant: bool
    error: Optional[str] = None


def verify_tls_version(
    resource_name: str,
    resource_type: str,
    min_required_version: TLSVersion = TLSVersion.TLS_1_3
) -> TLSCheckResult:
    """
    Verify TLS version for a resource.
    
    Args:
        resource_name: Name of the resource
        resource_type: Type of resource (api_gateway, vpc_endpoint, etc.)
        min_required_version: Minimum required TLS version
        
    Returns:
        TLSCheckResult with TLS version information
    """
    if resource_type == 'api_gateway':
        return _check_api_gateway_tls(resource_name, min_required_version)
    elif resource_type == 'vpc_endpoint':
        return _check_vpc_endpoint_tls(resource_name, min_required_version)
    else:
        return TLSCheckResult(
            resource_name=resource_name,
            resource_type=resource_type,
            min_tls_version=None,
            is_compliant=False,
            error=f'Unknown resource type: {resource_type}'
        )


def _check_api_gateway_tls(
    api_name: str,
    min_required_version: TLSVersion
) -> TLSCheckResult:
    """Check TLS version for API Gateway."""
    try:
        apigateway = boto3.client('apigateway')
        
        # List REST APIs to find the one we're looking for
        response = apigateway.get_rest_apis()
        apis = response.get('items', [])
        
        target_api = None
        for api in apis:
            if api.get('name') == api_name:
                target_api = api
                break
        
        if not target_api:
            return TLSCheckResult(
                resource_name=api_name,
                resource_type='api_gateway',
                min_tls_version=None,
                is_compliant=False,
                error=f'API {api_name} not found'
            )
        
        # API Gateway uses TLS 1.2 by default, TLS 1.3 when available
        # Check if minimum TLS version is set
        api_id = target_api.get('id')
        
        # Get stage information
        stages_response = apigateway.get_stages(restApiId=api_id)
        stages = stages_response.get('item', [])
        
        if not stages:
            return TLSCheckResult(
                resource_name=api_name,
                resource_type='api_gateway',
                min_tls_version=TLSVersion.TLS_1_2,
                is_compliant=False,
                error='No stages found'
            )
        
        # Check first stage for TLS settings
        stage = stages[0]
        
        # API Gateway doesn't expose TLS version directly in API
        # Assume TLS 1.2 minimum (AWS default)
        current_tls = TLSVersion.TLS_1_2
        
        is_compliant = _compare_tls_versions(current_tls, min_required_version) >= 0
        
        return TLSCheckResult(
            resource_name=api_name,
            resource_type='api_gateway',
            min_tls_version=current_tls,
            is_compliant=is_compliant
        )
    
    except ClientError as e:
        logger.error(f"Error checking API Gateway TLS: {e}")
        return TLSCheckResult(
            resource_name=api_name,
            resource_type='api_gateway',
            min_tls_version=None,
            is_compliant=False,
            error=str(e)
        )


def _check_vpc_endpoint_tls(
    endpoint_name: str,
    min_required_version: TLSVersion
) -> TLSCheckResult:
    """Check TLS version for VPC endpoint."""
    try:
        ec2 = boto3.client('ec2')
        
        # Describe VPC endpoints
        response = ec2.describe_vpc_endpoints()
        endpoints = response.get('VpcEndpoints', [])
        
        target_endpoint = None
        for endpoint in endpoints:
            if endpoint.get('ServiceName') == endpoint_name or \
               endpoint.get('VpcEndpointId') == endpoint_name:
                target_endpoint = endpoint
                break
        
        if not target_endpoint:
            return TLSCheckResult(
                resource_name=endpoint_name,
                resource_type='vpc_endpoint',
                min_tls_version=None,
                is_compliant=False,
                error=f'VPC endpoint {endpoint_name} not found'
            )
        
        # VPC endpoints use TLS 1.2 by default
        current_tls = TLSVersion.TLS_1_2
        
        is_compliant = _compare_tls_versions(current_tls, min_required_version) >= 0
        
        return TLSCheckResult(
            resource_name=endpoint_name,
            resource_type='vpc_endpoint',
            min_tls_version=current_tls,
            is_compliant=is_compliant
        )
    
    except ClientError as e:
        logger.error(f"Error checking VPC endpoint TLS: {e}")
        return TLSCheckResult(
            resource_name=endpoint_name,
            resource_type='vpc_endpoint',
            min_tls_version=None,
            is_compliant=False,
            error=str(e)
        )


def _compare_tls_versions(version1: TLSVersion, version2: TLSVersion) -> int:
    """
    Compare two TLS versions.
    
    Args:
        version1: First TLS version
        version2: Second TLS version
        
    Returns:
        Positive if version1 > version2, 0 if equal, negative if version1 < version2
    """
    version_order = [
        TLSVersion.TLS_1_0,
        TLSVersion.TLS_1_1,
        TLSVersion.TLS_1_2,
        TLSVersion.TLS_1_3
    ]
    
    idx1 = version_order.index(version1)
    idx2 = version_order.index(version2)
    
    return idx1 - idx2
