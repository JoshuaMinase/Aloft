# MongoDB Encryption at Rest Configuration

## Overview

MongoDB Atlas provides encryption at rest by default for all clusters. This document provides guidance on configuring and verifying encryption settings for production deployment.

## MongoDB Atlas Encryption (Recommended)

### 1. Default Encryption at Rest
MongoDB Atlas automatically encrypts data at rest using:
- **AES-256 encryption** for all data files
- **TLS 1.3** for data in transit
- **Automated key management** via AWS KMS, Azure Key Vault, or Google Cloud KMS

### 2. Configuration Steps

#### Step 1: Enable Encryption at Rest (Already Enabled by Default)
```bash
# In MongoDB Atlas Console:
# 1. Go to your cluster
# 2. Click "Security" tab
# 3. Verify "Encryption at Rest" is enabled (default)
```

#### Step 2: Enable Customer-Managed Keys (Optional - Enhanced Security)
```bash
# For additional security, use your own encryption keys:
# 1. Go to Security > Encryption at Rest
# 2. Click "Configure"
# 3. Select your KMS provider (AWS, Azure, or GCP)
# 4. Create or import your KMS key
# 5. Atlas will use your key to encrypt the master encryption key
```

#### Step 3: Enable Network Encryption (TLS)
```bash
# In MongoDB Atlas Console:
# 1. Go to your cluster
# 2. Click "Connect" > "Connect your application"
# 3. Use the connection string with "tls=true"
# Example: mongodb+srv://user:pass@cluster.mongodb.net/?tls=true
```

#### Step 4: Enable Audit Logs
```bash
# In MongoDB Atlas Console:
# 1. Go to your cluster
# 2. Click "Security" > "Audit Logs"
# 3. Enable audit logging
# 4. Configure log retention (recommended: 90 days)
# 5. Export logs to S3/Cloud Storage for long-term storage
```

### 3. Connection String Configuration

Update your `.env` file to enforce TLS:

```env
# MongoDB connection with TLS encryption
MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net/aloft?tls=true&tlsAllowInvalidCertificates=false&retryWrites=true&w=majority
```

**TLS Parameters:**
- `tls=true` - Enable TLS encryption
- `tlsAllowInvalidCertificates=false` - Require valid certificates (production)
- `retryWrites=true` - Retry write operations for durability
- `w=majority` - Write acknowledgment from majority of replicas

### 4. Application-Level Encryption (Optional)

For additional security, implement field-level encryption:

```python
# In app/core/encryption.py (if needed)
from cryptography.fernet import Fernet

class FieldEncryption:
    """Field-level encryption for sensitive data."""
    
    def __init__(self, key: str):
        self.cipher = Fernet(key.encode())
    
    def encrypt(self, data: str) -> str:
        """Encrypt a string field."""
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt a string field."""
        return self.cipher.decrypt(encrypted_data.encode()).decode()
```

## Application Configuration

### Environment Variables

Add these to your `.env` file:

```env
# MongoDB Security
MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net/aloft?tls=true&tlsAllowInvalidCertificates=false&retryWrites=true&w=majority
MONGODB_DB_NAME=aloft

# Encryption Key (for field-level encryption, if needed)
ENCRYPTION_KEY=your-32-byte-base64-encoded-key
```

### Security Best Practices

1. **Never commit connection strings to git**
   - Use environment variables
   - Use secret management tools (AWS Secrets Manager, HashiCorp Vault)

2. **Use IP Whitelisting**
   - In MongoDB Atlas, whitelist only trusted IP addresses
   - Use VPC peering for private network access

3. **Enable Role-Based Access Control**
   - Create least-privileged database users
   - Separate read/write permissions
   - Use Atlas Data Explorer to manage users

4. **Regular Security Audits**
   - Review access logs monthly
   - Rotate encryption keys quarterly
   - Update MongoDB driver versions

## Verification

### Test Encryption Status

```python
# Test script to verify encryption
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import get_settings

async def verify_encryption():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    
    # Check if TLS is enabled
    if "tls=true" in settings.mongodb_uri:
        print("✅ TLS encryption is enabled")
    else:
        print("❌ TLS encryption is NOT enabled")
    
    # Check connection
    try:
        await client.admin.command('ping')
        print("✅ Successfully connected to MongoDB")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(verify_encryption())
```

## Production Checklist

- [ ] MongoDB Atlas cluster created in production tier
- [ ] Encryption at rest enabled (default)
- [ ] TLS enabled in connection string
- [ ] IP whitelisting configured
- [ ] Audit logs enabled
- [ ] Role-based access control configured
- [ ] Database users with least privileges
- [ ] Backup schedule configured (daily)
- [ ] Point-in-time recovery enabled
- [ ] Cross-region replication (for disaster recovery)

## Compliance Notes

### GDPR Compliance
- Encryption at rest is a GDPR requirement
- Document encryption methods in your privacy policy
- Implement data retention policies in MongoDB

### CCPA Compliance
- Encryption helps demonstrate reasonable security measures
- Maintain audit logs for compliance verification
- Implement data deletion procedures

### SOC 2 Compliance
- Encryption at rest is a SOC 2 requirement
- Document encryption key management procedures
- Regular security audits recommended

## Troubleshooting

### Connection Issues with TLS
```bash
# If you see TLS certificate errors:
# 1. Ensure your system has up-to-date CA certificates
# 2. For development only, use tlsAllowInvalidCertificates=true
# 3. For production, use valid certificates
```

### Performance Impact
- Encryption at rest has minimal performance impact (<5%)
- TLS adds ~10-20ms latency per connection
- Use connection pooling to minimize overhead

## Resources

- [MongoDB Atlas Security Best Practices](https://www.mongodb.com/docs/atlas/security/)
- [MongoDB Encryption at Rest](https://www.mongodb.com/docs/manual/core/security-encryption-at-rest/)
- [MongoDB TLS/SSL Configuration](https://www.mongodb.com/docs/manual/core/security-transport-encryption/)
- [GDPR Compliance Guide](https://www.mongodb.com/blog/post/mongodb-and-gdpr-compliance)
