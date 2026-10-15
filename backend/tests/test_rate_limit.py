from nimbo.rate_limit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_rate_limiter_rejects_eleventh_request() -> None:
    limiter = RateLimiter(clock=FakeClock())

    results = [limiter.hit("1.1.1.1") for _ in range(11)]

    assert results[:10] == [None] * 10
    assert results[10] is not None


def test_rate_limiter_is_per_ip() -> None:
    limiter = RateLimiter(clock=FakeClock())
    for _ in range(10):
        limiter.hit("1.1.1.1")

    assert limiter.hit("1.1.1.1") is not None
    assert limiter.hit("2.2.2.2") is None


def test_rate_limiter_window_expires() -> None:
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    for _ in range(10):
        limiter.hit("1.1.1.1")
    assert limiter.hit("1.1.1.1") is not None

    clock.now += 60

    assert limiter.hit("1.1.1.1") is None


def test_rate_limiter_retry_after_seconds() -> None:
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    limiter.hit("1.1.1.1")  # oldest request at t=1000
    clock.now += 20.5
    for _ in range(9):
        limiter.hit("1.1.1.1")

    # oldest leaves the window at t=1060; now is t=1020.5 -> 39.5s -> 40
    assert limiter.hit("1.1.1.1") == 40
    clock.now += 39.5
    assert limiter.hit("1.1.1.1") is None
