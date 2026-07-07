# Database Backup and Recovery Guide

This guide covers MongoDB backup and recovery procedures for the Aloft backend.

## Overview

Regular database backups are critical for:

- Data protection against corruption or loss
- Disaster recovery
- Compliance requirements
- Point-in-time recovery
- Development/testing environments

## Backup Strategies

### Option 1: MongoDB Atlas Automated Backups (Recommended)

MongoDB Atlas provides automated backups with point-in-time recovery.

#### Configuration

1. **Enable Automated Backups**:
   - Go to MongoDB Atlas → Cluster → Backup
   - Click "Enable Automated Backups"
   - Configure retention period (1-90 days)
   - Set backup window (off-peak hours)

2. **Retention Policy**:
   ```bash
   # Production: 30-90 days
   # Staging: 14-30 days
   # Development: 7 days
   ```

3. **Backup Window**:
   ```bash
   # Set backup window during low traffic
   # Example: 2:00 AM - 6:00 AM UTC
   ```

#### Restoring from Atlas Backup

```bash
# Using Atlas CLI
atlas backups restore <cluster-name> \
  --snapshotId <snapshot-id> \
  --projectId <project-id>

# Using Atlas API
curl -X POST "https://cloud.mongodb.com/api/atlas/v1.0/groups/{projectId}/clusters/{clusterName}/backup/restoreJobs" \
  -H "Authorization: Bearer {API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "snapshotId": "{snapshotId}",
    "deliveryType": "automated"
  }'
```

### Option 2: mongodump for Manual Backups

For self-hosted MongoDB or additional backup control.

#### Manual Backup

```bash
# Basic backup
mongodump --uri="mongodb://user:pass@host:27017/aloft" --out=/backups/aloft-$(date +%Y%m%d)

# Backup with authentication
mongodump \
  --uri="mongodb://user:pass@host:27017/aloft" \
  --out=/backups/aloft-$(date +%Y%m%d) \
  --authenticationDatabase admin

# Compressed backup
mongodump \
  --uri="mongodb://user:pass@host:27017/aloft" \
  --out=/backups/aloft-$(date +%Y%m%d) \
  --gzip

# Backup specific collections
mongodump \
  --uri="mongodb://user:pass@host:27017/aloft" \
  --collection=users \
  --out=/backups/aloft-$(date +%Y%m%d)
```

#### Automated Backup Script

```bash
#!/bin/bash
# scripts/backup-mongodb.sh

# Configuration
MONGODB_URI="mongodb://user:pass@host:27017/aloft"
BACKUP_DIR="/backups/mongodb"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="$BACKUP_DIR/aloft-$DATE"

# Create backup directory
mkdir -p "$BACKUP_PATH"

# Perform backup
mongodump \
  --uri="$MONGODB_URI" \
  --out="$BACKUP_PATH" \
  --gzip

# Compress backup
tar -czf "$BACKUP_PATH.tar.gz" -C "$BACKUP_DIR" "aloft-$DATE"
rm -rf "$BACKUP_PATH"

# Remove old backups
find "$BACKUP_DIR" -name "aloft-*.tar.gz" -mtime +$RETENTION_DAYS -delete

# Log completion
echo "Backup completed: $BACKUP_PATH.tar.gz"

# Upload to cloud storage (optional)
# aws s3 cp "$BACKUP_PATH.tar.gz" s3://aloft-backups/mongodb/
```

#### Cron Job for Automated Backups

```bash
# Add to crontab
0 2 * * * /path/to/scripts/backup-mongodb.sh >> /var/log/mongodb-backup.log 2>&1
```

### Option 3: Database Snapshots (Cloud Provider)

For cloud-hosted MongoDB instances.

#### AWS EBS Snapshots

```bash
# Create EBS snapshot
aws ec2 create-snapshot \
  --volume-id <volume-id> \
  --description "MongoDB backup $(date +%Y%m%d)"

# List snapshots
aws ec2 describe-snapshots \
  --filters "Name=volume-id,Values=<volume-id>"

# Delete old snapshots
aws ec2 delete-snapshot --snapshot-id <snapshot-id>
```

#### DigitalOcean Snapshots

```bash
# Create snapshot
doctl compute volume snapshot <volume-id> \
  --snapshot-name "mongodb-backup-$(date +%Y%m%d)"

# List snapshots
doctl compute snapshot list

# Delete snapshot
doctl compute snapshot delete <snapshot-id>
```

## Recovery Procedures

### Recovery from mongodump

```bash
# Restore from backup
mongorestore \
  --uri="mongodb://user:pass@host:27017/aloft" \
  --gzip \
  /backups/aloft-20240101

# Restore to different database
mongorestore \
  --uri="mongodb://user:pass@host:27017/aloft_recovery" \
  --gzip \
  /backups/aloft-20240101

# Restore specific collection
mongorestore \
  --uri="mongodb://user:pass@host:27017/aloft" \
  --gzip \
  --collection=users \
  /backups/aloft-20240101/aloft/users.bson.gz
```

### Point-in-Time Recovery (Atlas)

```bash
# Restore to specific point in time
atlas clusters restore <cluster-name> \
  --timestamp "2024-01-01T12:00:00Z" \
  --projectId <project-id>
```

### Emergency Recovery Checklist

1. **Assess the situation**:
   - Identify data loss or corruption
   - Determine scope (single collection vs entire database)
   - Check when the issue occurred

2. **Stop application**:
   ```bash
   # Stop the application to prevent further data changes
   # docker-compose down
   # Or: systemctl stop aloft-backend
   ```

3. **Select backup**:
   - Choose the most recent clean backup
   - Verify backup integrity
   - Document backup source and timestamp

4. **Perform restore**:
   ```bash
   # Test restore to staging first
   mongorestore --uri="mongodb://staging-host:27017/aloft" /backups/test-restore
   
   # If successful, restore to production
   mongorestore --uri="mongodb://production-host:27017/aloft" /backups/production-restore
   ```

5. **Verify data**:
   - Check data integrity
   - Run application tests
   - Verify key functionality

6. **Restart application**:
   ```bash
   # Start the application
   # docker-compose up -d
   # Or: systemctl start aloft-backend
   ```

7. **Monitor**:
   - Monitor application logs
   - Check error rates
   - Verify user-facing functionality

## Backup Best Practices

### DO ✓

- Perform regular automated backups
- Test backup restoration regularly
- Use multiple backup destinations (local + cloud)
- Encrypt backups at rest and in transit
- Monitor backup success/failure
- Document backup procedures
- Implement appropriate retention policies
- Use off-site storage for disaster recovery
- Secure backup access with proper permissions
- Maintain backup logs and documentation

### DON'T ✗

- Never skip backups during maintenance
- Never store backups on the same server as the database
- Never use unencrypted backups for sensitive data
- Never test restore procedures in production
- Never ignore backup failures
- Never store backup credentials in the backup itself
- Never delete backups without verification
- Never rely on a single backup method
- Never forget to backup configuration files
- Never skip monitoring backup processes

## Backup Monitoring

### Health Checks

```python
# scripts/check-backup-health.py
import os
import subprocess
from datetime import datetime, timedelta

def check_latest_backup():
    """Check if latest backup is recent enough."""
    backup_dir = "/backups/mongodb"
    max_age_hours = 26  # Backup should be within 26 hours
    
    # Get latest backup
    backups = sorted([f for f in os.listdir(backup_dir) if f.startswith("aloft-")])
    if not backups:
        raise Exception("No backups found")
    
    latest_backup = backups[-1]
    backup_time = datetime.strptime(latest_backup.split("-")[1], "%Y%m%d_%H%M%S")
    age = datetime.now() - backup_time
    
    if age > timedelta(hours=max_age_hours):
        raise Exception(f"Latest backup is {age} old (max: {max_age_hours}h)")
    
    print(f"Backup check passed: {latest_backup} ({age} old)")

def check_backup_size():
    """Check if backup size is reasonable."""
    backup_dir = "/backups/mongodb"
    min_size_mb = 100  # Minimum expected backup size
    
    backups = sorted([f for f in os.listdir(backup_dir) if f.endswith(".tar.gz")])
    if not backups:
        raise Exception("No compressed backups found")
    
    latest_backup = backups[-1]
    backup_path = os.path.join(backup_dir, latest_backup)
    size_mb = os.path.getsize(backup_path) / (1024 * 1024)
    
    if size_mb < min_size_mb:
        raise Exception(f"Backup size {size_mb}MB is too small (min: {min_size_mb}MB)")
    
    print(f"Backup size check passed: {size_mb:.2f}MB")

if __name__ == "__main__":
    try:
        check_latest_backup()
        check_backup_size()
        print("All backup health checks passed")
    except Exception as e:
        print(f"Backup health check failed: {e}")
        exit(1)
```

### Alerting

```python
# Setup alerting for backup failures
import logging
from app.core.logging_config import log_security_event

def log_backup_failure(error: str):
    """Log backup failure for monitoring."""
    log_security_event(
        event_type="BACKUP_FAILURE",
        severity="critical",
        error=error,
        timestamp=datetime.utcnow().isoformat()
    )
```

## Cloud Storage Integration

### AWS S3 Backup Storage

```bash
# Upload backup to S3
aws s3 cp /backups/aloft-20240101.tar.gz \
  s3://aloft-backups/mongodb/aloft-20240101.tar.gz \
  --server-side-encryption AES256

# List backups
aws s3 ls s3://aloft-backups/mongodb/

# Download backup
aws s3 cp s3://aloft-backups/mongodb/aloft-20240101.tar.gz /backups/

# Enable lifecycle policy for old backups
aws s3api put-bucket-lifecycle-configuration \
  --bucket aloft-backups \
  --lifecycle-configuration file://lifecycle.json
```

`lifecycle.json`:
```json
{
  "Rules": [
    {
      "Id": "DeleteOldBackups",
      "Status": "Enabled",
      "Prefix": "mongodb/",
      "Expiration": {
        "Days": 90
      }
    }
  ]
}
```

### Cloudflare R2 Backup Storage

```python
# Python script for R2 backup
import boto3
import os

s3 = boto3.client(
    's3',
    endpoint_url='https://<account-id>.r2.cloudflarestorage.com',
    aws_access_key_id='<access-key-id>',
    aws_secret_access_key='<secret-access-key>'
)

def upload_backup_to_r2(backup_path: str):
    """Upload backup to Cloudflare R2."""
    filename = os.path.basename(backup_path)
    s3.upload_file(
        backup_path,
        'aloft-backups',
        f'mongodb/{filename}',
        ExtraArgs={'ServerSideEncryption': 'AES256'}
    )
    print(f"Uploaded {filename} to R2")
```

## Disaster Recovery

### Disaster Recovery Plan

1. **Recovery Time Objective (RTO)**: 4 hours
2. **Recovery Point Objective (RPO)**: 1 hour
3. **Backup Locations**: 
   - Primary: MongoDB Atlas automated backups
   - Secondary: Daily mongodump to S3
   - Tertiary: Weekly EBS snapshots

### Disaster Recovery Procedure

1. **Declare disaster**:
   - Assess impact
   - Notify stakeholders
   - Initiate disaster recovery team

2. **Assess backup status**:
   - Verify latest backup integrity
   - Check backup age
   - Select appropriate backup source

3. **Provision infrastructure**:
   - Spin up new MongoDB instance
   - Configure networking
   - Set up security groups

4. **Restore database**:
   - Restore from backup
   - Verify data integrity
   - Run consistency checks

5. **Update application configuration**:
   - Update MongoDB URI
   - Restart application
   - Verify connectivity

6. **Switch DNS (if needed)**:
   - Update DNS records
   - Monitor propagation
   - Verify endpoint resolution

7. **Monitor and validate**:
   - Monitor application logs
   - Check error rates
   - Validate user functionality

8. **Post-incident review**:
   - Document incident
   - Analyze root cause
   - Update procedures

## Compliance

### GDPR

- Data retention: 90 days (configurable)
- Right to erasure: Implement data deletion from backups
- Data portability: Export backup data on request
- Breach notification: Report within 72 hours

### HIPAA

- Backup encryption: Required
- Access controls: Role-based access
- Audit logging: Track all backup/restore operations
- Business associate agreements: For backup providers

### SOC 2

- Backup frequency: Daily
- Retention policy: 30-90 days
- Access logging: Comprehensive audit trail
- Testing: Quarterly restore tests

## Troubleshooting

### Common Issues

**Backup fails with authentication error:**
```bash
Error: Authentication failed
```
**Solution**: Verify MongoDB credentials and connection string.

**Restore fails with space error:**
```bash
Error: No space left on device
```
**Solution**: Free disk space or restore to larger volume.

**Backup is too large:**
```bash
Backup size: 50GB (expected: 5GB)
```
**Solution**: Check for unexpected data growth, consider collection-specific backups.

**Restore is slow:**
```bash
Restore taking 6+ hours
```
**Solution**: Use `--parallel` option for faster restore, consider indexes after restore.

## Additional Resources

- [MongoDB Backup Best Practices](https://www.mongodb.com/docs/manual/administration/backup-restore/)
- [MongoDB Atlas Backup](https://www.mongodb.com/docs/atlas/backup/)
- [AWS Backup Documentation](https://docs.aws.amazon.com/backup/)
- [Disaster Recovery Planning](https://www.drplan.org/)
