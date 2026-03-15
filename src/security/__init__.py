"""Security controls module for Multi-Agent Advisory AI System."""

from src.security.encryption import (
    verify_dynamodb_encryption,
    verify_s3_encryption,
    verify_opensearch_encryption,
    EncryptionStatus
)
from src.security.authorization import (
    AuthorizationChecker,
    check_user_access,
    enforce_user_isolation
)
from src.security.audit_logging import (
    AuditLogger,
    log_agent_action,
    log_data_access
)
from src.security.tls_config import (
    verify_tls_version,
    TLSVersion
)

__all__ = [
    'verify_dynamodb_encryption',
    'verify_s3_encryption',
    'verify_opensearch_encryption',
    'EncryptionStatus',
    'AuthorizationChecker',
    'check_user_access',
    'enforce_user_isolation',
    'AuditLogger',
    'log_agent_action',
    'log_data_access',
    'verify_tls_version',
    'TLSVersion'
]
