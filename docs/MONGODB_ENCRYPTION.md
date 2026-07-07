# MongoDB Encryption at Rest Guide

This guide covers implementing encryption at rest for MongoDB in the Aloft backend to protect sensitive data.

## Overview

MongoDB encryption at rest protects data stored in database files by encrypting the data before it's written to disk and decrypting it when read into memory. This is essential for:

- Compliance with data protection regulations (GDPR, HIPAA, SOC 2)
- Protection against unauthorized data access
- Defense against physical data theft
- Secure cloud storage

## Encryption Options

### Option 1: MongoDB Atlas Encryption (Recommended)

MongoDB Atlas provides built-in encryption at rest with AWS, GCP, and Azure integration.

#### Setup for MongoDB Atlas

1. **Enable Encryption at Rest**:
   - Go to MongoDB Atlas → Project → Security → Encryption at Rest
   - Click "Enable Encryption at Rest"
   - Choose your cloud provider (AWS, GCP, or Azure)
   - Select or create a KMS key

2. **AWS KMS Configuration**:
   ```bash
   # Create AWS KMS key
   aws kms create-key \
     --description "Aloft MongoDB encryption key" \
     --key-usage ENCRYPT_DECRYPT
   
   # Get key ARN
   aws kms describe-keys \
     --key-id <key-id>
   ```

3. **Atlas Configuration**:
   - In Atlas, select "AWS KMS" as encryption provider
   - Enter your AWS KMS key ARN
   - Configure IAM role for Atlas to access KMS
   - Enable encryption

4. **Verify Encryption**:
   ```bash
   # Check encryption status via Atlas CLI
   atlas clusters describe <cluster-name> --projectId <project-id>
   ```

#### Connection String Configuration

Update your MongoDB URI to use TLS for encryption in transit:

```python
# app/core/config.py
mongodb_uri: str = (
    "mongodb+srv://user:pass@cluster.mongodb.net/aloft?"
    "retryWrites=true&w=majority&tls=true"
)
```

### Option 2: MongoDB Enterprise Encryption

For self-hosted MongoDB Enterprise, use MongoDB's native encryption.

#### Configuration

1. **Enable Encryption in mongod.conf**:
   ```yaml
   # mongod.conf
   security:
     enableEncryption: true
     encryptionKeyFile: /etc/mongodb-keyfile
   ```

2. **Generate Encryption Key**:
   ```bash
   # Generate 96-byte key file
   openssl rand -base64 96 > /etc/mongodb-keyfile
   chmod 400 /etc/mongodb-keyfile
   chown mongodb:mongodb /etc/mongodb-keyfile
   ```

3. **Start MongoDB with Encryption**:
   ```bash
   mongod --config /etc/mongod.conf
   ```

### Option 3: Volume/Filesystem Encryption

Encrypt the underlying storage volume or filesystem.

#### AWS EBS Encryption

```bash
# Create encrypted EBS volume
aws ec2 create-volume \
  --size 100 \
  --availability-zone us-east-1a \
  --encrypted \
  --kms-key-id <kms-key-id>

# Attach to instance
aws ec2 attach-volume \
  --volume-id <volume-id> \
  --instance-id <instance-id> \
  --device /dev/sdf
```

#### Docker Volume Encryption

```yaml
# docker-compose.yml
version: '3.8'
services:
  mongodb:
    image: mongo:7.0
    volumes:
      - mongodb_data:/data/db
    # Use encrypted volumes in production

volumes:
  mongodb_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /encrypted/mongodb/path
```

## Field-Level Encryption

For additional security, implement field-level encryption for sensitive data.

### Client-Side Field Level Encryption (CSFLE)

```python
# Add to requirements.txt
pymongo==4.10.1
mongocrypt==1.12.0

# app/core/encryption.py
from pymongo.encryption import ClientEncryption
from pymongo.encryption_options import AutoEncryptionOpts
from pymongo import MongoClient

def create_encrypted_client():
    """Create MongoDB client with field-level encryption."""
    
    # KMS provider configuration (AWS)
    kms_providers = {
        "aws": {
            "accessKeyId": os.getenv("AWS_ACCESS_KEY_ID"),
            "secretAccessKey": os.getenv("AWS_SECRET_ACCESS_KEY"),
        }
    }
    
    # Data key and key vault configuration
    key_vault_namespace = ("encryption.__keyVault")
    auto_encryption_opts = AutoEncryptionOpts(
        kms_providers=kms_providers,
        key_vault_namespace=key_vault_namespace,
    )
    
    # Create client with encryption
    client = MongoClient(
        get_settings().mongodb_uri,
        auto_encryption_opts=auto_encryption_opts
    )
    
    return client

# Example: Encrypt sensitive fields
def encrypt_user_data(user_data: dict) -> dict:
    """Encrypt sensitive user fields."""
    
    encrypted_fields = {
        "email": user_data["email"],
        "phone": user_data.get("phone"),
        "emergency_contact": user_data.get("emergency_contact"),
    }
    
    # Fields to encrypt
    encryption_schema = {
        "fields": [
            {
                "path": "email",
                "keyId": "<data-key-id>",
                "bsonType": "string",
                "algorithms": ["AEAD_AES_256_CBC_HMAC_SHA_512-Deterministic"]
            },
            {
                "path": "phone",
                "keyId": "<data-key-id>",
                "bsonType": "string",
                "algorithms": ["AEAD_AES_256_CBC_HMAC_SHA_512-Random"]
            }
        ]
    }
    
    return encrypted_fields
```

### Queryable Encryption

MongoDB 6.0+ supports queryable encryption for encrypted field queries.

```python
# Configure queryable encryption
encrypted_fields_map = {
    "users": {
        "fields": [
            {
                "path": "email",
                "keyId": "<data-key-id>",
                "bsonType": "string",
                "queries": {"queryType": "equality"}
            }
        ]
    }
}

auto_encryption_opts = AutoEncryptionOpts(
    kms_providers=kms_providers,
    key_vault_namespace=key_vault_namespace,
    encrypted_fields_map=encrypted_fields_map
)
```

## Application-Level Encryption

For additional security, encrypt sensitive data before storage.

### Using PyCryptodome

```python
# Add to requirements.txt
pycryptodome==3.20.0

# app/core/encryption.py
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Random import get_random_bytes
import base64
import os

class DataEncryption:
    """Application-level data encryption."""
    
    def __init__(self):
        self.key = self._get_encryption_key()
        self.salt = os.getenv("ENCRYPTION_SALT", "").encode()
    
    def _get_encryption_key(self) -> bytes:
        """Derive encryption key from environment variable."""
        password = os.getenv("DATA_ENCRYPTION_KEY")
        if not password:
            raise ValueError("DATA_ENCRYPTION_KEY must be set")
        
        key = PBKDF2(
            password,
            self.salt,
            dkLen=32,
            count=100000
        )
        return key
    
    def encrypt(self, data: str) -> str:
        """Encrypt string data."""
        cipher = AES.new(self.key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(data.encode())
        
        # Combine nonce, tag, and ciphertext
        encrypted = cipher.nonce + tag + ciphertext
        return base64.b64encode(encrypted).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt string data."""
        encrypted = base64.b64decode(encrypted_data.encode())
        
        # Extract nonce, tag, and ciphertext
        nonce = encrypted[:16]
        tag = encrypted[16:32]
        ciphertext = encrypted[32:]
        
        cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
        data = cipher.decrypt_and_verify(ciphertext, tag)
        return data.decode()

# Usage
encryption = DataEncryption()

# Encrypt before storing
user["email"] = encryption.encrypt(user["email"])

# Decrypt after retrieval
user["email"] = encryption.decrypt(user["email"])
```

## Configuration

### Environment Variables

```bash
# MongoDB Atlas Encryption
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/aloft?tls=true

# Field-Level Encryption (AWS KMS)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_KMS_KEY_ID=arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012

# Application-Level Encryption
DATA_ENCRYPTION_KEY=your-32-byte-encryption-key
ENCRYPTION_SALT=your-random-salt
```

### Application Configuration

```python
# app/core/config.py
class Settings(BaseSettings):
    # ... existing fields ...
    
    # Encryption configuration
    enable_encryption_at_rest: bool = True
    enable_field_level_encryption: bool = False
    enable_application_level_encryption: bool = False
    
    # KMS configuration
    aws_access_key_id: str | None = None
    aws_secret_access_key: SecretStr | None = None
    aws_kms_key_id: str | None = None
    
    # Application encryption
    data_encryption_key: SecretStr | None = None
    encryption_salt: str = "default-salt-change-in-production"
```

## Best Practices

### DO ✓

- Enable encryption at rest in production
- Use TLS for encryption in transit
- Rotate encryption keys annually
- Use separate keys for different environments
- Implement key management policies
- Monitor encryption key access
- Back up encryption keys securely
- Test encryption/decryption regularly
- Document encryption procedures
- Use hardware security modules (HSM) for key storage

### DON'T ✗

- Never store encryption keys in code
- Never use default encryption keys
- Never disable encryption in production
- Never hardcode encryption parameters
- Never share encryption keys via email
- Never commit encryption keys to git
- Never use weak encryption algorithms
- Never ignore encryption errors
- Never skip key rotation
- Never test encryption on production data

## Key Rotation

### MongoDB Atlas Key Rotation

```bash
# Rotate AWS KMS key
aws kms enable-key-rotation --key-id <key-id>

# Update Atlas to use new key
# In Atlas: Security → Encryption at Rest → Update KMS key
```

### Application Key Rotation

```python
# Rotate application encryption key
def rotate_encryption_key(old_key: str, new_key: str):
    """Rotate encryption key and re-encrypt data."""
    
    old_encryption = DataEncryption()
    old_encryption.key = old_key
    
    new_encryption = DataEncryption()
    new_encryption.key = new_key
    
    # Re-encrypt all sensitive data
    users = get_db()["users"].find()
    for user in users:
        # Decrypt with old key
        decrypted_email = old_encryption.decrypt(user["email"])
        
        # Encrypt with new key
        encrypted_email = new_encryption.encrypt(decrypted_email)
        
        # Update database
        get_db()["users"].update_one(
            {"_id": user["_id"]},
            {"$set": {"email": encrypted_email}}
        )
```

## Compliance

### GDPR

- Encrypt personal data at rest
- Implement data retention policies
- Enable right to erasure
- Document data processing
- Report data breaches within 72 hours

### HIPAA

- Encrypt protected health information (PHI)
- Implement access controls
- Audit all data access
- Business associate agreements
- Risk assessments

### SOC 2

- Encrypt all sensitive data
- Implement access logging
- Regular security reviews
- Incident response procedures
- Vendor risk management

## Monitoring

### Encryption Status Monitoring

```python
# Monitor encryption status
def check_encryption_status():
    """Check if encryption is properly configured."""
    
    settings = get_settings()
    
    # Check encryption at rest
    if not settings.enable_encryption_at_rest:
        log_security_event(
            event_type="ENCRYPTION_DISABLED",
            severity="critical",
            message="Encryption at rest is disabled"
        )
    
    # Check key configuration
    if settings.enable_field_level_encryption:
        if not settings.aws_kms_key_id:
            log_security_event(
                event_type="ENCRYPTION_KEY_MISSING",
                severity="critical",
                message="KMS key ID not configured"
            )
    
    # Check application encryption
    if settings.enable_application_level_encryption:
        if not settings.data_encryption_key:
            log_security_event(
                event_type="ENCRYPTION_KEY_MISSING",
                severity="critical",
                message="Application encryption key not configured"
            )
```

### Key Access Monitoring

```python
# Monitor key access (AWS CloudWatch)
import boto3

cloudwatch = boto3.client('cloudwatch')

# Create metric for key access
cloudwatch.put_metric_data(
    Namespace='MongoDB/Encryption',
    MetricData=[{
        'MetricName': 'KeyAccessCount',
        'Value': 1,
        'Unit': 'Count'
    }]
)
```

## Troubleshooting

### Common Issues

**Encryption at rest not enabled:**
```
Error: Data is not encrypted at rest
```
**Solution**: Enable encryption in MongoDB Atlas or configure MongoDB Enterprise encryption.

**KMS key access denied:**
```
Error: AccessDenied when accessing KMS key
```
**Solution**: Check IAM role permissions and KMS key policy.

**Field-level encryption errors:**
```
Error: Unable to encrypt field
```
**Solution**: Verify data key exists and KMS provider is configured correctly.

**Performance degradation:**
```
Error: Slow queries after enabling encryption
```
**Solution**: Encryption adds overhead; consider indexing strategy and query optimization.

## Additional Resources

- [MongoDB Atlas Encryption](https://www.mongodb.com/docs/atlas/security/encryption-at-rest/)
- [MongoDB Enterprise Encryption](https://www.mongodb.com/docs/manual/core/security-encryption-at-rest/)
- [AWS KMS Documentation](https://docs.aws.amazon.com/kms/)
- [MongoDB Client-Side Field Level Encryption](https://www.mongodb.com/docs/manual/core/security-client-side-encryption/)
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)
