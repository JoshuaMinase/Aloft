"""Secret management module for secure credential handling.

This module provides a unified interface for retrieving secrets from various sources:
- Environment variables (default)
- AWS Secrets Manager
- Azure Key Vault
- Google Secret Manager

Usage:
    from app.core.secrets import get_secret
    
    # Automatically detects the secret source based on configuration
    api_key = get_secret("GROQ_API_KEY")
    
    # Or specify a source explicitly
    api_key = get_secret("GROQ_API_KEY", source="aws_secrets_manager")
"""

import os
import logging
from typing import Optional
from functools import lru_cache

logger = logging.getLogger("aloft.secrets")


class SecretSource:
    """Available secret sources."""
    ENVIRONMENT = "environment"
    AWS_SECRETS_MANAGER = "aws_secrets_manager"
    AZURE_KEY_VAULT = "azure_key_vault"
    GOOGLE_SECRET_MANAGER = "google_secret_manager"


def get_secret(
    secret_name: str,
    source: Optional[str] = None,
    default: Optional[str] = None,
) -> str:
    """Retrieve a secret from the configured source.
    
    Args:
        secret_name: Name of the secret to retrieve
        source: Secret source to use (auto-detected if None)
        default: Default value if secret is not found
        
    Returns:
        The secret value
        
    Raises:
        ValueError: If secret is not found and no default is provided
    """
    # Auto-detect source if not specified
    if source is None:
        source = _detect_secret_source()
    
    # Route to appropriate secret backend
    if source == SecretSource.ENVIRONMENT:
        return _get_from_environment(secret_name, default=default)
    elif source == SecretSource.AWS_SECRETS_MANAGER:
        return _get_from_aws_secrets_manager(secret_name, default=default)
    elif source == SecretSource.AZURE_KEY_VAULT:
        return _get_from_azure_key_vault(secret_name, default=default)
    elif source == SecretSource.GOOGLE_SECRET_MANAGER:
        return _get_from_google_secret_manager(secret_name, default=default)
    else:
        logger.warning(f"Unknown secret source: {source}, falling back to environment")
        return _get_from_environment(secret_name, default=default)


def _detect_secret_source() -> str:
    """Auto-detect the appropriate secret source based on environment."""
    # Check for AWS environment
    if os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"):
        try:
            import boto3
            # Verify AWS credentials are available
            boto3.client("sts").get_caller_identity()
            logger.info("Detected AWS environment, using AWS Secrets Manager")
            return SecretSource.AWS_SECRETS_MANAGER
        except Exception as e:
            logger.debug(f"AWS detected but credentials not available: {e}")
    
    # Check for Azure environment
    if os.getenv("AZURE_CLIENT_ID") or os.getenv("AZURE_TENANT_ID"):
        logger.info("Detected Azure environment, using Azure Key Vault")
        return SecretSource.AZURE_KEY_VAULT
    
    # Check for Google environment
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("GOOGLE_CLOUD_PROJECT"):
        logger.info("Detected Google Cloud environment, using Google Secret Manager")
        return SecretSource.GOOGLE_SECRET_MANAGER
    
    # Default to environment variables
    logger.debug("Using environment variables as secret source")
    return SecretSource.ENVIRONMENT


def _get_from_environment(secret_name: str, default: Optional[str] = None) -> str:
    """Retrieve secret from environment variables."""
    value = os.getenv(secret_name, default)
    if value is None:
        raise ValueError(f"Secret {secret_name} not found in environment and no default provided")
    return value


def _get_from_aws_secrets_manager(secret_name: str, default: Optional[str] = None) -> str:
    """Retrieve secret from AWS Secrets Manager."""
    try:
        import boto3
        
        client = boto3.client("secretsmanager")
        # Try to get the secret - secret_name can be the full ARN or just the name
        try:
            response = client.get_secret_value(SecretId=secret_name)
            return response["SecretString"]
        except client.exceptions.ResourceNotFoundException:
            # Try appending a common prefix if not found
            prefixed_name = f"aloft/{secret_name}"
            try:
                response = client.get_secret_value(SecretId=prefixed_name)
                return response["SecretString"]
            except client.exceptions.ResourceNotFoundException:
                if default is not None:
                    logger.warning(f"Secret {secret_name} not found in AWS Secrets Manager, using default")
                    return default
                raise ValueError(f"Secret {secret_name} not found in AWS Secrets Manager")
    except ImportError:
        logger.warning("boto3 not installed, falling back to environment variables")
        return _get_from_environment(secret_name, default=default)
    except Exception as e:
        logger.error(f"Error retrieving secret from AWS Secrets Manager: {e}")
        if default is not None:
            return default
        raise


def _get_from_azure_key_vault(secret_name: str, default: Optional[str] = None) -> str:
    """Retrieve secret from Azure Key Vault."""
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
        
        vault_url = os.getenv("AZURE_KEY_VAULT_URL")
        if not vault_url:
            logger.warning("AZURE_KEY_VAULT_URL not set, falling back to environment variables")
            return _get_from_environment(secret_name, default=default)
        
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=vault_url, credential=credential)
        
        try:
            secret = client.get_secret(secret_name)
            return secret.value
        except Exception:
            # Try with common prefix
            prefixed_name = f"aloft-{secret_name}"
            try:
                secret = client.get_secret(prefixed_name)
                return secret.value
            except Exception:
                if default is not None:
                    logger.warning(f"Secret {secret_name} not found in Azure Key Vault, using default")
                    return default
                raise ValueError(f"Secret {secret_name} not found in Azure Key Vault")
    except ImportError:
        logger.warning("azure-identity or azure-keyvault-secrets not installed, falling back to environment variables")
        return _get_from_environment(secret_name, default=default)
    except Exception as e:
        logger.error(f"Error retrieving secret from Azure Key Vault: {e}")
        if default is not None:
            return default
        raise


def _get_from_google_secret_manager(secret_name: str, default: Optional[str] = None) -> str:
    """Retrieve secret from Google Secret Manager."""
    try:
        from google.cloud import secretmanager
        
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            logger.warning("GOOGLE_CLOUD_PROJECT not set, falling back to environment variables")
            return _get_from_environment(secret_name, default=default)
        
        client = secretmanager.SecretManagerServiceClient()
        
        # Try different name formats
        name_formats = [
            f"projects/{project_id}/secrets/{secret_name}/versions/latest",
            f"projects/{project_id}/secrets/aloft-{secret_name}/versions/latest",
        ]
        
        for name in name_formats:
            try:
                response = client.access_secret_version(name=name)
                return response.payload.data.decode("UTF-8")
            except Exception:
                continue
        
        if default is not None:
            logger.warning(f"Secret {secret_name} not found in Google Secret Manager, using default")
            return default
        raise ValueError(f"Secret {secret_name} not found in Google Secret Manager")
    except ImportError:
        logger.warning("google-cloud-secret-manager not installed, falling back to environment variables")
        return _get_from_environment(secret_name, default=default)
    except Exception as e:
        logger.error(f"Error retrieving secret from Google Secret Manager: {e}")
        if default is not None:
            return default
        raise


@lru_cache
def validate_secrets_configured() -> dict[str, bool]:
    """Validate that all required secrets are configured.
    
    Returns a dictionary mapping secret names to whether they are configured.
    """
    required_secrets = [
        "JWT_SECRET_KEY",
        "MONGODB_URI",
    ]
    
    optional_secrets = [
        "GROQ_API_KEY",
        "ELEVENLABS_API_KEY",
        "AVIATIONSTACK_API_KEY",
        "REDIS_URL",
        "RESEND_API_KEY",
        "SENDGRID_API_KEY",
    ]
    
    results = {}
    
    for secret in required_secrets:
        try:
            value = get_secret(secret)
            results[secret] = bool(value and value != "change-me-in-production-use-secrets-token-hex-32")
        except Exception:
            results[secret] = False
    
    for secret in optional_secrets:
        try:
            value = get_secret(secret, default=None)
            results[secret] = bool(value)
        except Exception:
            results[secret] = False
    
    return results


def log_secret_validation_results() -> None:
    """Log the results of secret validation for debugging."""
    results = validate_secrets_configured()
    
    configured = [name for name, is_set in results.items() if is_set]
    missing = [name for name, is_set in results.items() if not is_set]
    
    if configured:
        logger.info(f"Configured secrets: {', '.join(configured)}")
    if missing:
        logger.warning(f"Missing secrets: {', '.join(missing)}")