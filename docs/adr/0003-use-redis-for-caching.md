# ADR 0003: Use Redis for Caching and Session Management

## Status

Accepted

## Context

The Aloft application requires:

- Rate limiting to protect API endpoints
- Session management for flight tracking
- Caching of frequently accessed data
- Background job queue for content generation
- Real-time data coordination

These requirements demand:

- Fast read/write operations
- TTL (time-to-live) support for automatic expiration
- Atomic operations for rate limiting
- Simple data structures for caching

## Decision

We will use **Redis** for caching, session management, and rate limiting.

### Rationale

1. **Performance**: In-memory storage provides microsecond-level response times
2. **TTL Support**: Built-in expiration for sessions and rate limits
3. **Atomic Operations**: INCR/DECR operations perfect for rate limiting
4. **Data Structures**: Hashes, sets, and sorted sets for complex caching
5. **Persistence**: Optional persistence for durability
6. **Scalability**: Easy to scale via clustering
7. **Ecosystem**: Strong Python client support

### Alternatives Considered

- **Memcached**: Fast but lacks persistence and advanced data structures
- **In-Memory Python**: Not shared across processes, no persistence
- **MongoDB**: Slower for caching, higher cost for simple operations

## Consequences

### Positive

- Extremely fast rate limiting and session operations
- Automatic expiration prevents memory bloat
- Atomic operations prevent race conditions
- Supports advanced caching patterns
- Graceful degradation when unavailable

### Negative

- Additional infrastructure component
- Memory-based (requires sufficient RAM)
- Data loss if persistence is disabled
- Additional operational complexity

## Implementation

Redis is accessed via the redis-py library:
```
redis==5.2.1
```

Connection management is in `app/core/redis.py` and `app/core/redis_client.py`.

## Graceful Degradation

When Redis is unavailable, the application degrades gracefully:

- Rate limiting fails open (allows requests)
- Sessions fall back to in-memory storage
- Caching is disabled
- Background jobs are skipped

This ensures the application remains functional even if Redis is down.

## References

- [Redis Documentation](https://redis.io/docs/)
- [Redis-py Documentation](https://redis-py.readthedocs.io/)
- [Redis Rate Limiting](https://redis.io/docs/manual/patterns/rate-limit/)
