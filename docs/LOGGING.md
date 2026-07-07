# Centralized Logging Guide

This guide covers the centralized logging implementation for the Aloft backend, including correlation IDs, structured logging, and log aggregation integration.

## Overview

The Aloft backend uses structured logging with correlation ID support to enable:

- Distributed tracing across requests
- Easy log aggregation and analysis
- Security event monitoring
- Performance metrics tracking
- Error tracking and debugging

## Features

### Correlation IDs

Each HTTP request gets a unique correlation ID that's propagated through:

- **Incoming requests**: Extracted from `X-Correlation-ID` header or generated
- **Application logs**: Automatically included in all log entries
- **External API calls**: Should be forwarded to downstream services
- **Error tracking**: Links all logs for a single request

### Structured Logging

Logs are emitted in structured format (JSON in production, console in development):

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "info",
  "logger": "aloft.api",
  "correlation_id": "abc-123-def",
  "event_type": "api_request",
  "method": "POST",
  "path": "/v1/routes/pois",
  "user_id": "user-123",
  "duration_ms": 245.5
}
```

### Log Levels

- **DEBUG**: Detailed diagnostic information
- **INFO**: General informational messages
- **WARNING**: Warning messages for potential issues
- **ERROR**: Error events that might still allow the application to continue
- **CRITICAL**: Critical events that require immediate attention

## Configuration

### Environment Variables

```bash
# Log level (default: INFO)
LOG_LEVEL=INFO

# Environment (affects log format)
ENVIRONMENT=production  # JSON logs
ENVIRONMENT=development  # Console logs
```

### Setup

Logging is automatically configured on application startup:

```python
from app.core.logging_config import setup_logging, get_logger

# Configure logging (called automatically in app/main.py)
setup_logging(
    environment="production",
    log_level="INFO",
    log_format="json"
)

# Get a logger
logger = get_logger(__name__)
```

## Usage

### Basic Logging

```python
from app.core.logging_config import get_logger

logger = get_logger(__name__)

logger.info("User logged in", user_id="user-123")
logger.warning("Rate limit approaching", ip="192.168.1.1")
logger.error("Database connection failed", error="Connection timeout")
```

### Structured Logging

```python
logger.info(
    "API request completed",
    endpoint="/v1/routes/pois",
    method="POST",
    status_code=200,
    duration_ms=123.4,
    user_id="user-123"
)
```

### Security Events

```python
from app.core.logging_config import log_security_event

log_security_event(
    event_type="RATE_LIMIT_VIOLATION",
    severity="warning",
    user_id="user-123",
    ip="192.168.1.1",
    endpoint="/v1/routes/pois",
    method="POST"
)
```

### API Errors

```python
from app.core.logging_config import log_api_error

log_api_error(
    endpoint="/v1/routes/pois",
    method="POST",
    status_code=500,
    error="Internal server error",
    user_id="user-123",
    exception_type="ValueError"
)
```

### Performance Metrics

```python
from app.core.logging_config import log_performance_metric
import time

start_time = time.time()
# ... perform operation ...
duration_ms = (time.time() - start_time) * 1000

log_performance_metric(
    operation="database_query",
    duration_ms=duration_ms,
    success=True,
    query_type="find_pois"
)
```

## Log Aggregation

### Render Logs (Default)

Render automatically captures stdout and makes logs available in the dashboard:

1. Go to your Render service
2. Click "Logs" tab
3. View real-time logs with correlation IDs
4. Filter by correlation ID to trace requests

### AWS CloudWatch

For AWS deployments, send logs to CloudWatch:

```python
# Add to requirements.txt
aws-lambda-logging==0.3.1

# Configure in app/core/logging_config.py
import aws_lambda_logging

def setup_logging():
    aws_lambda_logging.setup(
        level=get_settings().log_level,
        service_name="aloft-backend"
    )
```

### Datadog

For Datadog integration:

```python
# Add to requirements.txt
ddtrace==2.5.0

# Configure in app/core/logging_config.py
from ddtrace import patch

# Patch libraries for tracing
patch(fastapi=True, pymongo=True, redis=True)

# Configure Datadog logging
import logging
from ddtrace import tracer

class DatadogHandler(logging.Handler):
    def emit(self, record):
        tracer.log(
            message=self.format(record),
            level=record.levelname,
            extra=record.__dict__
        )

# Add handler to root logger
logging.root.addHandler(DatadogHandler())
```

### Logstash/ELK

For Logstash integration:

```python
# Add to requirements.txt
python-logstash==0.4.0

# Configure in app/core/logging_config.py
import logstash

handler = logstash.TCPLogstashHandler(
    host='logstash.example.com',
    port=5959,
    version=1
)

logging.root.addHandler(handler)
```

## Distributed Tracing

### Correlation ID Propagation

The middleware automatically handles correlation IDs:

```python
# Incoming request with correlation ID
curl -H "X-Correlation-ID: abc-123" https://api.aloft.app/v1/routes/pois

# Correlation ID is logged in all subsequent log entries
# {"correlation_id": "abc-123", ...}
```

### External API Calls

Forward correlation ID to external services:

```python
import httpx
from app.core.logging_config import correlation_id

async def call_external_api():
    correlation_id_value = correlation_id.get()
    headers = {}
    if correlation_id_value:
        headers["X-Correlation-ID"] = correlation_id_value
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.example.com/data",
            headers=headers
        )
    return response
```

## Log Analysis

### Common Queries

**Find all logs for a specific request:**
```bash
# In Render logs
filter: correlation_id = "abc-123"

# In CloudWatch Insights
fields @timestamp, @message
| filter correlation_id = "abc-123"
| sort @timestamp desc
```

**Find all security events:**
```bash
# Render logs
filter: logger = "aloft.security"

# CloudWatch Insights
fields @timestamp, event_type, severity, user_id, ip
| filter logger = "aloft.security"
| sort @timestamp desc
```

**Find slow operations:**
```bash
# CloudWatch Insights
fields @timestamp, operation, duration_ms
| filter logger = "aloft.performance" and duration_ms > 1000
| sort duration_ms desc
```

**Find errors by endpoint:**
```bash
# CloudWatch Insights
fields @timestamp, endpoint, method, status_code, error
| filter logger = "aloft.api" and status_code >= 400
| stats count() by endpoint
```

## Monitoring and Alerting

### Key Metrics to Monitor

1. **Error rate**: Percentage of requests resulting in errors
2. **Response time**: Average request duration
3. **Security events**: Rate of security-related events
4. **Log volume**: Unexpected spikes in log volume
5. **Correlation ID patterns**: Failed requests with same correlation ID

### Alert Configuration

**Render Alerts:**
1. Go to your Render service
2. Click "Alerts" tab
3. Set up alerts for:
   - Error rate > 1%
   - Response time > 1s
   - Security event rate spike

**CloudWatch Alarms:**
```python
# Using AWS CloudWatch
import boto3

cloudwatch = boto3.client('cloudwatch')

cloudwatch.put_metric_alarm(
    AlarmName='aloft-error-rate',
    MetricName='Errors',
    Namespace='Aloft/API',
    Statistic='Sum',
    Period=300,
    EvaluationPeriods=1,
    Threshold=10,
    ComparisonOperator='GreaterThanThreshold'
)
```

## Best Practices

### DO ✓

- Use structured logging with context
- Include correlation IDs in all logs
- Log security events with appropriate severity
- Use appropriate log levels
- Include performance metrics
- Avoid logging sensitive data
- Use correlation IDs for distributed tracing
- Set up log aggregation and monitoring
- Regularly review and analyze logs

### DON'T ✗

- Never log passwords, API keys, or secrets
- Never log PII (Personally Identifiable Information)
- Never use print() statements for logging
- Never ignore error logs
- Never log at DEBUG level in production
- Never log large objects in full
- Never log in hot loops without sampling
- Never ignore correlation IDs

## Troubleshooting

### Logs Not Appearing

**Check log level:**
```bash
# Ensure LOG_LEVEL is set appropriately
LOG_LEVEL=DEBUG  # For development
LOG_LEVEL=INFO   # For production
```

**Check logging configuration:**
```python
# Verify logging is configured
import logging
print(logging.root.level)  # Should be 10 (DEBUG), 20 (INFO), etc.
```

**Check middleware order:**
```python
# Ensure LoggingMiddleware is first in middleware chain
app.add_middleware(LoggingMiddleware)  # Should be first
```

### Correlation IDs Missing

**Check middleware is enabled:**
```python
# Ensure LoggingMiddleware is added
app.add_middleware(LoggingMiddleware)
```

**Check client is sending header:**
```bash
# Include correlation ID in requests
curl -H "X-Correlation-ID: abc-123" https://api.aloft.app/v1/routes/pois
```

### Structlog Not Working

**Check structlog is installed:**
```bash
pip install structlog
```

**Check fallback is working:**
```python
# The system falls back to standard logging if structlog is not available
# Logs will still work, just without structlog features
```

## Performance Considerations

### Log Sampling

For high-traffic endpoints, consider log sampling:

```python
import random

def should_log_sample(sample_rate: float = 0.1) -> bool:
    """Return True with given probability."""
    return random.random() < sample_rate

# Usage
if should_log_sample(0.1):  # Log 10% of requests
    logger.info("Request details", ...)
```

### Async Logging

For high-performance scenarios, use async logging:

```python
# Add to requirements.txt
aiologger==0.7.0

from aiologger import Logger
from aiologger.handlers.files import AsyncFileHandler

logger = Logger.with_default_handlers(
    name='aloft',
    level='INFO',
    handler=AsyncFileHandler(filename='app.log')
)
```

## Security Considerations

### Sensitive Data

Never log sensitive information:

```python
# BAD
logger.info("User login", password="secret123")

# GOOD
logger.info("User login", user_id="user-123", success=True)
```

### Log Retention

Configure appropriate log retention policies:

- **Development**: 7 days
- **Staging**: 30 days
- **Production**: 90 days (or as required by compliance)

### Log Access

Control access to logs:

- Use role-based access control
- Audit log access
- Encrypt logs at rest
- Secure log transmission

## Additional Resources

- [Structlog Documentation](https://www.structlog.org/)
- [Python Logging Guide](https://docs.python.org/3/howto/logging.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [Render Logs Documentation](https://render.com/docs/logs)
- [CloudWatch Logs Documentation](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/)
