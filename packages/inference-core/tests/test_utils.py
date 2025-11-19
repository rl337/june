from inference_core import (
    serialize_json,
    deserialize_json,
    Timer,
    RateLimiter,
    RetryConfig,
    retry_sync,
    HealthChecker,
    get_timestamp,
    generate_id,
)


def test_serialize_roundtrip():
    obj = {"a": 1, "b": "x"}
    s = serialize_json(obj)
    assert deserialize_json(s) == obj


def test_rate_limiter_allows_then_blocks():
    rl = RateLimiter(2, time_window=1.0)
    assert rl.is_allowed()
    assert rl.is_allowed()
    assert not rl.is_allowed()


def test_retry_sync_succeeds_after_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("fail")
        return 42

    assert retry_sync(flaky, config=RetryConfig(max_attempts=3, base_delay=0.01)) == 42


def test_health_checker():
    import asyncio

    hc = HealthChecker()
    hc.add_check("ok", lambda: True)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(hc.check_all())
        assert results["ok"] is True
    finally:
        loop.close()


def test_helpers():
    ts = get_timestamp()
    gid = generate_id()
    assert isinstance(ts, str) and len(ts) > 0
    assert isinstance(gid, str) and len(gid) > 0
