# Secrets Management Guide

This guide covers production-grade secrets management for the Aloft backend.

## Overview

Secrets management is critical for application security. This guide covers:

- Environment-based secrets configuration
- Production secrets management services
- Secret rotation procedures
- Best practices for handling sensitive data

## Current Implementation

The Aloft backend uses environment variables for secrets management with Pydantic's `SecretStr` for sensitive values:

```python
# app/core/config.py
groq_api_key: SecretStr | None = None
elevenlabs_api_key: SecretStr | None = None
jwt_secret_key: SecretStr = SecretStr(_JWT_DEFAULT)
```

### Security Features

- **Type-safe secrets**: Using `SecretStr` prevents accidental logging
- **Production validation**: Refuses to start with default secrets in production
- **CORS validation**: Prevents wildcard CORS in production
- **Environment-specific configuration**: Different settings for dev/staging/production

## Production Secrets Management Options

### Option 1: Render Environment Variables (Recommended for Render Deployments)

Render provides built-in secrets management through environment variables.

**Setup:**
1. Go to your Render dashboard
2. Select your service → Settings → Environment Variables
3. Add each secret as an environment variable

**Secrets to Configure:**
```bash
# Core
ENVIRONMENT=production
JWT_SECRET_KEY=<generate-with-secrets-token-hex-32>
MONGODB_URI=<your-mongodb-atlas-connection-string>
REDIS_URL=<your-redis-cloud-connection-string>

# API Keys
GROQ_API_KEY=<your-groq-api-key>
ELEVENLABS_API_KEY=<your-elevenlabs-api-key>
AVIATIONSTACK_API_KEY=<your-aviationstack-api-key>

# CORS
CORS_ALLOWED_ORIGINS=["https://aloft.app","https://www.aloft.app"]

# Optional: Cloudflare R2
R2_ACCOUNT_ID=<your-r2-account-id>
R2_ACCESS_KEY_ID=<your-r2-access-key-id>
R2_SECRET_ACCESS_KEY=<your-r2-secret-access-key>
R2_BUCKET_NAME=<your-r2-bucket-name>
```

**Pros:**
- Native to Render platform
- Automatic injection into container
- No additional infrastructure
- Easy to rotate via dashboard

**Cons:**
- Platform-specific
- Limited audit logging
- No version history

### Option 2: AWS Secrets Manager (Recommended for AWS Deployments)

For AWS-based deployments, use AWS Secrets Manager for enhanced security.

**Setup:**
```python
# Add to requirements.txt
boto3==1.35.99
```

**Configuration:**
```python
# app/core/config.py
from functools import lru_cache
import boto3
import json
from botocore.exceptions import ClientError

class Settings(BaseSettings):
    # ... existing fields ...
    
    # AWS Secrets Manager
    aws_secret_name: str | None = None
    aws_region: str = "us-east-1"

    def _get_secret_from_aws(self, secret_name: str) -> dict:
        """Retrieve secret from AWS Secrets Manager."""
        client = boto3.client('secretsmanager', region_name=self.aws_region)
        
        try:
            response = client.get_secret_value(SecretId=secret_name)
            if 'SecretString' in response:
                return json.loads(response['SecretString'])
            else:
                return json.loads(response['SecretBinary'])
        except ClientError as e:
            raise ValueError(f"Failed to retrieve secret from AWS: {e}")

@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    
    # Load secrets from AWS if configured
    if settings.aws_secret_name:
        secrets = settings._get_secret_from_aws(settings.aws_secret_name)
        # Override settings with secrets
        for key, value in secrets.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
    
    return settings
```

**AWS Secret Structure:**
```json
{
  "GROQ_API_KEY": "your-key",
  "ELEVENLABS_API_KEY": "your-key",
  "JWT_SECRET_KEY": "your-secret",
  "MONGODB_URI": "your-connection-string",
  "REDIS_URL": "your-redis-url"
}
```

**Pros:**
- Automatic secret rotation
- Fine-grained IAM policies
- Audit logging via CloudTrail
- Version history
- Encryption at rest

**Cons:**
- AWS-specific
- Additional cost
- More complex setup

### Option 3: HashiCorp Vault (Enterprise-Grade)

For enterprise deployments requiring advanced secret management.

**Setup:**
```python
# Add to requirements.txt
hvac==2.3.0
```

**Configuration:**
```python
import hvac

class Settings(BaseSettings):
    vault_addr: str | None = None
    vault_token: str | None = None
    vault_secret_path: str | None = None

    def _get_secret_from_vault(self) -> dict:
        """Retrieve secret from HashiCorp Vault."""
        client = hvac.Client(url=self.vault_addr, token=self.vault_token)
        
        if not client.is_authenticated():
            raise ValueError("Failed to authenticate with Vault")
        
        response = client.secrets.kv.v2.read_secret_version(
            path=self.vault_secret_path
        )
        
        return response['data']['data']
```

**Pros:**
- Advanced features (dynamic secrets, encryption as a service)
- Multi-cloud support
- Comprehensive audit logging
- Secret versioning

**Cons:**
- Complex setup and maintenance
- Requires dedicated infrastructure
- Higher operational overhead

## Secret Rotation Procedures

### API Key Rotation

**When to Rotate:**
- On a regular schedule (quarterly recommended)
- When a key is compromised
- When an employee with access leaves
- When upgrading to a higher-tier plan

**Rotation Process:**

1. **Generate new key** in the provider's dashboard
2. **Add new key** to secrets manager (don't remove old one yet)
3. **Deploy application** with new key
4. **Monitor** for errors for 24-48 hours
5. **Remove old key** from secrets manager
6. **Revoke old key** in provider's dashboard

**Example for Groq API:**
```bash
# 1. Generate new key in Groq dashboard
# 2. Add to Render as GROQ_API_KEY_NEW
# 3. Update deployment to use new key
# 4. Monitor logs for authentication errors
# 5. Remove old GROQ_API_KEY
# 6. Revoke old key in Groq dashboard
```

### JWT Secret Rotation

**When to Rotate:**
- Immediately if suspected compromise
- Annually as a security best practice
- When changing encryption algorithms

**Rotation Process:**

1. **Generate new secret**:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

2. **Support both secrets** during transition:
   ```python
   # app/core/config.py
   jwt_secret_key: SecretStr = SecretStr(_JWT_DEFAULT)
   jwt_secret_key_previous: SecretStr | None = None  # For rotation
   ```

3. **Update authentication** to try both secrets:
   ```python
   # In your JWT validation logic
   def decode_token(token: str):
       try:
           return jwt.decode(token, settings.jwt_secret_key.get_secret_value(), ...)
       except JWTError:
           if settings.jwt_secret_key_previous:
               return jwt.decode(token, settings.jwt_secret_key_previous.get_secret_value(), ...)
           raise
   ```

4. **Deploy** with both secrets configured
5. **Wait** for token expiration (default 30 minutes)
6. **Remove** old secret
7. **Deploy** without old secret

### Database Connection String Rotation

**When to Rotate:**
- Database user password changes
- Database cluster migration
- Security audit requirements

**Rotation Process:**

1. **Create new database user** with strong password
2. **Grant necessary permissions** to new user
3. **Update connection string** in secrets manager
4. **Deploy application** with new credentials
5. **Monitor** for connection errors
6. **Delete old database user** after successful transition

## Secrets in Development

### Local Development

For local development, use a `.env` file (never commit to git):

```bash
# .env
ENVIRONMENT=development
JWT_SECRET_KEY=dev-secret-key-not-for-production
MONGODB_URI=mongodb://localhost:27017/?directConnection=true
REDIS_URL=redis://localhost:6379/0
GROQ_API_KEY=your-dev-key
ELEVENLABS_API_KEY=your-dev-key
```

### Multiple Environments

Use separate `.env` files for different environments:

```bash
# .env.development
ENVIRONMENT=development
JWT_SECRET_KEY=dev-secret

# .env.staging
ENVIRONMENT=staging
JWT_SECRET_KEY=staging-secret

# .env.production
ENVIRONMENT=production
JWT_SECRET_KEY=prod-secret
```

Load environment-specific file:
```python
from dotenv import load_dotenv
import os

env = os.getenv("ENVIRONMENT", "development")
load_dotenv(f".env.{env}")
```

## Best Practices

### DO ✓

- Use environment variables for all secrets
- Use `SecretStr` for sensitive Pydantic fields
- Rotate secrets regularly
- Use different secrets for different environments
- Implement secret validation at startup
- Use read-only credentials where possible
- Implement principle of least privilege
- Audit secret access logs
- Use strong, randomly generated secrets

### DON'T ✗

- Never commit secrets to git
- Never log secrets (use SecretStr)
- Never share secrets via email/chat
- Never use the same secret across environments
- Never hardcode secrets in code
- Never store secrets in config files
- Never use weak or predictable secrets
- Never ignore secret rotation
- Never disable secret validation

## Secret Generation

### Generate Strong Secrets

```bash
# JWT Secret (32 bytes = 64 hex characters)
python -c "import secrets; print(secrets.token_hex(32))"

# API Key-like secret (32 bytes, URL-safe base64)
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Database password (24 characters, mixed case)
python -c "import secrets; import string; print(''.join(secrets.choice(string.ascii_letters + string.digits + string.punctuation) for _ in range(24)))"
```

### Password Requirements

- **Minimum length**: 24 characters
- **Character types**: Uppercase, lowercase, numbers, symbols
- **Uniqueness**: Different for each service/environment
- **Randomness**: Use cryptographically secure random generator

## Monitoring and Alerting

### Secret Access Monitoring

Monitor for:
- Unexpected secret access patterns
- Failed authentication attempts
- Configuration changes
- Secret rotation events

### Alerting

Set up alerts for:
- Secret access failures
- Configuration validation errors
- Secret expiration warnings
- Unauthorized access attempts

## Compliance

### SOC 2 / ISO 27001

- Document secret management procedures
- Implement secret rotation schedule
- Maintain audit logs
- Regular security reviews
- Access control policies

### GDPR / HIPAA

- Encrypt secrets at rest
- Encrypt secrets in transit
- Implement data retention policies
- Right to erasure considerations
- Data breach notification procedures

## Troubleshooting

### Common Issues

**Application won't start with default secrets:**
```
ValueError: JWT_SECRET_KEY must be changed from the default before running in production
```
**Solution**: Generate and set a strong JWT_SECRET_KEY in your environment.

**CORS wildcard in production:**
```
ValueError: CORS_ALLOWED_ORIGINS cannot be ['*'] in production
```
**Solution**: Set CORS_ALLOWED_ORIGINS to your actual frontend domains.

**Secret not being loaded:**
- Check environment variable name matches exactly
- Verify secret is set in secrets manager
- Check application logs for loading errors
- Validate IAM permissions (for AWS Secrets Manager)

## Additional Resources

- [OWASP Secrets Management](https://owasp.org/www-community/Secrets_Management_Cheat_Sheet)
- [Render Environment Variables](https://render.com/docs/environment-variables)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/)
- [HashiCorp Vault](https://www.vaultproject.io/docs)
- [Twelve-Factor App: Config](https://12factor.net/config)
