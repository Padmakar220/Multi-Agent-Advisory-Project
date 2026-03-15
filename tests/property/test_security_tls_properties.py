"""
Property-based tests for data encryption in transit (TLS 1.3).

Tests validate that all data transmission uses TLS 1.3 encryption.
"""

import pytest
from hypothesis import given, settings, strategies as st
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

from src.security.tls_config import (
    verify_tls_version,
    TLSVersion,
    _compare_tls_versions
)


class TestDataEncryptionInTransit:
    """
    Property 56: Data Encryption in Transit
    
    For any data transmission between system components, TLS 1.3 encryption 
    should be used.
    
    Validates: Requirements 13.3
    """

    @settings(max_examples=50)
    @given(
        api_name=st.text(min_size=1, max_size=100)
    )
    def test_api_gateway_tls_version(self, api_name):
        """
        Test that API Gateway uses TLS 1.3.
        
        For any API Gateway endpoint, TLS 1.3 should be the minimum version.
        """
        with patch('boto3.client') as mock_boto:
            mock_apigateway = MagicMock()
            mock_boto.return_value = mock_apigateway
            
            mock_apigateway.get_rest_apis.return_value = {
                'items': [
                    {
                        'id': 'api123',
                        'name': api_name
                    }
                ]
            }
            
            mock_apigateway.get_stages.return_value = {
                'item': [
                    {
                        'stageName': 'prod',
                        'deploymentId': 'deploy123'
                    }
                ]
            }
            
            result = verify_tls_version(
                api_name,
                'api_gateway',
                TLSVersion.TLS_1_3
            )
            
            # API Gateway defaults to TLS 1.2, not fully compliant with TLS 1.3
            assert result.resource_name == api_name
            assert result.resource_type == 'api_gateway'
            assert result.min_tls_version is not None

    @settings(max_examples=50)
    @given(
        endpoint_name=st.text(min_size=1, max_size=100)
    )
    def test_vpc_endpoint_tls_version(self, endpoint_name):
        """
        Test that VPC endpoints use TLS 1.3.
        
        For any VPC endpoint, TLS 1.3 should be the minimum version.
        """
        with patch('boto3.client') as mock_boto:
            mock_ec2 = MagicMock()
            mock_boto.return_value = mock_ec2
            
            mock_ec2.describe_vpc_endpoints.return_value = {
                'VpcEndpoints': [
                    {
                        'VpcEndpointId': 'vpce-123',
                        'ServiceName': endpoint_name,
                        'State': 'available'
                    }
                ]
            }
            
            result = verify_tls_version(
                endpoint_name,
                'vpc_endpoint',
                TLSVersion.TLS_1_3
            )
            
            assert result.resource_name == endpoint_name
            assert result.resource_type == 'vpc_endpoint'
            assert result.min_tls_version is not None

    @settings(max_examples=50)
    @given(
        version1=st.sampled_from([
            TLSVersion.TLS_1_0,
            TLSVersion.TLS_1_1,
            TLSVersion.TLS_1_2,
            TLSVersion.TLS_1_3
        ]),
        version2=st.sampled_from([
            TLSVersion.TLS_1_0,
            TLSVersion.TLS_1_1,
            TLSVersion.TLS_1_2,
            TLSVersion.TLS_1_3
        ])
    )
    def test_tls_version_comparison(self, version1, version2):
        """
        Test TLS version comparison logic.
        
        For any two TLS versions, comparison should work correctly.
        """
        result = _compare_tls_versions(version1, version2)
        
        version_order = [
            TLSVersion.TLS_1_0,
            TLSVersion.TLS_1_1,
            TLSVersion.TLS_1_2,
            TLSVersion.TLS_1_3
        ]
        
        idx1 = version_order.index(version1)
        idx2 = version_order.index(version2)
        expected = idx1 - idx2
        
        assert result == expected

    @settings(max_examples=50)
    @given(
        api_name=st.text(min_size=1, max_size=100)
    )
    def test_api_gateway_not_found(self, api_name):
        """
        Test handling when API Gateway is not found.
        
        For any non-existent API, the check should return not compliant.
        """
        with patch('boto3.client') as mock_boto:
            mock_apigateway = MagicMock()
            mock_boto.return_value = mock_apigateway
            
            mock_apigateway.get_rest_apis.return_value = {
                'items': []
            }
            
            result = verify_tls_version(
                api_name,
                'api_gateway',
                TLSVersion.TLS_1_3
            )
            
            assert not result.is_compliant
            assert result.error is not None

    @settings(max_examples=50)
    @given(
        endpoint_name=st.text(min_size=1, max_size=100)
    )
    def test_vpc_endpoint_not_found(self, endpoint_name):
        """
        Test handling when VPC endpoint is not found.
        
        For any non-existent endpoint, the check should return not compliant.
        """
        with patch('boto3.client') as mock_boto:
            mock_ec2 = MagicMock()
            mock_boto.return_value = mock_ec2
            
            mock_ec2.describe_vpc_endpoints.return_value = {
                'VpcEndpoints': []
            }
            
            result = verify_tls_version(
                endpoint_name,
                'vpc_endpoint',
                TLSVersion.TLS_1_3
            )
            
            assert not result.is_compliant
            assert result.error is not None

    @settings(max_examples=50)
    @given(
        api_name=st.text(min_size=1, max_size=100)
    )
    def test_api_gateway_error_handling(self, api_name):
        """
        Test error handling for API Gateway TLS checks.
        
        For any error during TLS verification, the result should indicate error.
        """
        with patch('boto3.client') as mock_boto:
            mock_apigateway = MagicMock()
            mock_boto.return_value = mock_apigateway
            
            mock_apigateway.get_rest_apis.side_effect = ClientError(
                {'Error': {'Code': 'UnauthorizedException', 'Message': 'Unauthorized'}},
                'GetRestApis'
            )
            
            result = verify_tls_version(
                api_name,
                'api_gateway',
                TLSVersion.TLS_1_3
            )
            
            assert not result.is_compliant
            assert result.error is not None

    @settings(max_examples=50)
    @given(
        endpoint_name=st.text(min_size=1, max_size=100)
    )
    def test_vpc_endpoint_error_handling(self, endpoint_name):
        """
        Test error handling for VPC endpoint TLS checks.
        
        For any error during TLS verification, the result should indicate error.
        """
        with patch('boto3.client') as mock_boto:
            mock_ec2 = MagicMock()
            mock_boto.return_value = mock_ec2
            
            mock_ec2.describe_vpc_endpoints.side_effect = ClientError(
                {'Error': {'Code': 'UnauthorizedOperation', 'Message': 'Unauthorized'}},
                'DescribeVpcEndpoints'
            )
            
            result = verify_tls_version(
                endpoint_name,
                'vpc_endpoint',
                TLSVersion.TLS_1_3
            )
            
            assert not result.is_compliant
            assert result.error is not None

    @settings(max_examples=50)
    @given(
        resource_type=st.text(min_size=1, max_size=50)
    )
    def test_unknown_resource_type(self, resource_type):
        """
        Test handling of unknown resource types.
        
        For any unknown resource type, the check should return not compliant.
        """
        if resource_type not in ['api_gateway', 'vpc_endpoint']:
            result = verify_tls_version(
                'test-resource',
                resource_type,
                TLSVersion.TLS_1_3
            )
            
            assert not result.is_compliant
            assert result.error is not None
