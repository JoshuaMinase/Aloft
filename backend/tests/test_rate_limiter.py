"""
Unit tests for services/rate_limiter.py -- pure logic against a fakeredis
instance, no real Redis required. These run entirely in-process.

Eight tests covering:
- Normal allow behavior under the limit
- Blocking behavior once the limit is exceeded
- Key independence (different keys have independent limits)
- Window expiry and reset
- The expiry-only-on-first-request invariant (regression test for a
  specific bug: unconditional EXPIRE on every call would keep pushing
  the window forward forever so the limit would never reset)
- Fail-open when redis_client is None
- Fail-open when a Redis call raises an exception
- retry_after_seconds on the RateLimitExceeded exception
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
import redis.asyncio as redis

from app.services.rate_limiter import RateLimitExceeded, check_rate_limit


@pytest.fixture
async def fake_redis():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


async def test_allows_requests_under_the_limit(fake_redis):
    for _ in range(3):
        await check_rate_limit(fake_redis, "test-key", max_requests=5, window_seconds=60)
    # No exception raised -- all 3 requests, under the limit of 5, succeeded.


async def test_raises_once_the_limit_is_exceeded(fake_redis):
    for _ in range(3):
        await check_rate_limit(fake_redis, "test-key", max_requests=3, window_seconds=60)

    with pytest.raises(RateLimitExceeded):
        await check_rate_limit(fake_redis, "test-key", max_requests=3, window_seconds=60)


async def test_different_keys_have_independent_limits(fake_redis):
    for _ in range(3):
        await check_rate_limit(fake_redis, "key-a", max_requests=3, window_seconds=60)

    # key-b has never been called -- should still be allowed, completely
    # independent of key-a's exhausted limit.
    await check_rate_limit(fake_redis, "key-b", max_requests=3, window_seconds=60)


async def test_window_actually_expires_and_resets_the_count(fake_redis):
    await check_rate_limit(fake_redis, "test-key", max_requests=1, window_seconds=60)

    with pytest.raises(RateLimitExceeded):
        await check_rate_limit(fake_redis, "test-key", max_requests=1, window_seconds=60)

    # Manually expire the key to simulate the window passing, rather than
    # actually sleeping 60s in a test.
    await fake_redis.delete("test-key")

    # Should succeed again now that the "window" has reset.
    await check_rate_limit(fake_redis, "test-key", max_requests=1, window_seconds=60)


async def test_expiry_is_only_set_on_the_first_request_in_a_window(fake_redis):
    """If EXPIRE were called unconditionally on every request, a client
    making requests faster than the window length would keep pushing the
    expiry forward forever and the limit would never reset. This is the
    one test that would catch that regression.
    """
    await check_rate_limit(fake_redis, "test-key", max_requests=10, window_seconds=100)
    ttl_after_first = await fake_redis.ttl("test-key")

    # Simulate time passing within the window (TTL ticking down) without
    # actually sleeping -- set it manually to a known lower value.
    await fake_redis.expire("test-key", 50)

    await check_rate_limit(fake_redis, "test-key", max_requests=10, window_seconds=100)
    ttl_after_second = await fake_redis.ttl("test-key")

    # The second call must NOT have reset the TTL back up to ~100 --
    # it should still reflect the manually-lowered value from above.
    assert ttl_after_second <= 50
    assert ttl_after_first > ttl_after_second


async def test_fails_open_when_redis_client_is_none():
    # No exception, no blocking -- a request should succeed even when
    # Redis isn't configured/reachable at all.
    await check_rate_limit(None, "test-key", max_requests=0, window_seconds=60)


async def test_fails_open_when_redis_call_raises():
    broken_client = AsyncMock(spec=redis.Redis)
    # Simulate the pipeline itself raising on execute
    mock_pipe = AsyncMock()
    mock_pipe.set = AsyncMock()
    mock_pipe.incr = AsyncMock()
    mock_pipe.execute = AsyncMock(side_effect=redis.ConnectionError("Redis is down"))
    broken_client.pipeline.return_value = mock_pipe

    # Should not raise RateLimitExceeded OR propagate the ConnectionError
    # -- a Redis outage should never take the whole app down with it.
    await check_rate_limit(broken_client, "test-key", max_requests=1, window_seconds=60)


async def test_rate_limit_exceeded_carries_a_sensible_retry_after(fake_redis):
    await check_rate_limit(fake_redis, "test-key", max_requests=1, window_seconds=60)

    with pytest.raises(RateLimitExceeded) as exc_info:
        await check_rate_limit(fake_redis, "test-key", max_requests=1, window_seconds=60)

    assert 0 < exc_info.value.retry_after_seconds <= 60
