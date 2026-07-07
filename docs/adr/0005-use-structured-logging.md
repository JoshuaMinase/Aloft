# ADR 0005: Use Structured Logging with Correlation IDs

## Status

Accepted

## Context

The Aloft application requires comprehensive logging for:

- Debugging and troubleshooting
- Security event monitoring
- Performance analysis
- Distributed tracing across microservices
- Compliance and audit requirements

Challenges with traditional logging:

- Unstructured text logs are hard to parse and analyze
- No correlation between related log entries
- Difficult to aggregate and search across logs
- Limited context in log messages
- Hard to trace requests across service boundaries

## Decision

We will use **structured logging with correlation IDs** using structlog.

### Rationale

1. **Structured Format**: JSON logs are machine-readable and easy to parse
2. **Correlation IDs**: Unique IDs trace requests across all log entries
3. **Context**: Rich context in each log entry (user_id, endpoint, etc.)
4. **Aggregation**: Easy to send to log aggregators (CloudWatch, Datadog, etc.)
5. **Analysis**: Simple to query and analyze log data
6. **Distributed Tracing**: Correlation IDs enable request tracing
7. **Security Events**: Structured security event logging for monitoring

### Alternatives Considered

- **Standard Python Logging**: Unstructured text, limited context
- **Custom JSON Logging**: More code to maintain, less feature-rich
- **Third-Party Logging Services**: Vendor lock-in, higher cost

## Consequences

### Positive

- Easy to search and filter logs
- Better debugging with request tracing
- Simplified log aggregation
- Rich context in each log entry
- Better security monitoring
- Production-ready JSON format

### Negative

- Additional dependency (structlog)
- Slightly more verbose logging code
- Requires log viewer for human readability in production

## Implementation

Structured logging is implemented via structlog:
```
structlog==24.4.0
```

Configuration is in `app/core/logging_config.py` with middleware in `app/middleware/security.py`.

## Log Format

**Development** (human-readable):
```
2024-01-15 10:30:45 [INFO] aloft.api - User logged in user_id=user-123
```

**Production** (JSON):
```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "info",
  "logger": "aloft.api",
  "correlation_id": "abc-123-def",
  "event": "user_logged_in",
  "user_id": "user-123"
}
```

## Correlation ID Flow

1. Incoming request receives or generates correlation ID
2. ID is added to logging context via middleware
3. All log entries include the correlation ID
4. ID is forwarded to external API calls
5. Enables end-to-end request tracing

## References

- [Structlog Documentation](https://www.structlog.org/)
- [Structured Logging Best Practices](https://www.ibm.com/docs/en/ibm-mq/9.1.0?topic=tel-structured-logging-best-practices)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
