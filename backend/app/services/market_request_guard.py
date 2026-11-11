from __future__ import annotations

import random
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import wraps
from typing import Any, Callable


class SourceBlockedError(RuntimeError):
    def __init__(self, message: str, retry_after_seconds: float = 2700):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def retry_after_seconds(value: str | None) -> float:
    if not value:
        return 0
    try:
        return max(0, float(value))
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0


def is_rate_limit_error(error: BaseException) -> bool:
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        status = getattr(current, "status_code", None)
        response = getattr(current, "response", None)
        if status in {403, 412, 429} or getattr(response, "status_code", None) in {403, 412, 429}:
            return True
        message = str(current).lower()
        if isinstance(current, SourceBlockedError) or any(
            marker in message or marker in type(current).__name__.lower()
            for marker in ("ratelimit", "rate limit", "too many requests", "captcha", "限流", "封禁", "验证码", "访问过于频繁")
        ):
            return True
        pending.extend(item for item in current.args if isinstance(item, BaseException))
        pending.extend(item for item in (current.__cause__, current.__context__) if item is not None)
    return False


class RequestThrottle:
    """同一进程的 AKShare 请求串行执行，分页和重试也需经过此处。"""

    def __init__(
        self,
        interval: float = 5,
        jitter: float = 3,
        cooldown: float = 2700,
        batch_size: int = 50,
        batch_pause: float = 60,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        uniform: Callable[[float, float], float] = random.uniform,
    ):
        self.interval = interval
        self.jitter = jitter
        self.cooldown = cooldown
        self.batch_size = batch_size
        self.batch_pause = batch_pause
        self.sleep = sleep
        self.clock = clock
        self.uniform = uniform
        self.lock = threading.Lock()
        self.last_finished: float | None = None
        self.blocked_until = 0.0
        self.requests = 0

    def call(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        with self.lock:
            if self.clock() < self.blocked_until:
                raise SourceBlockedError("数据源处于风控冷却期，请稍后续采", self.blocked_until - self.clock())
            if self.last_finished is not None:
                delay = self.interval + self.uniform(0, self.jitter)
                if self.requests and self.requests % self.batch_size == 0:
                    delay = max(delay, self.batch_pause)
                remaining = self.last_finished + delay - self.clock()
                if remaining > 0:
                    self.sleep(remaining)
            self.requests += 1
            try:
                response = function(*args, **kwargs)
                if getattr(response, "status_code", None) in {403, 412, 429}:
                    wait = retry_after_seconds(getattr(response, "headers", {}).get("Retry-After"))
                    raise SourceBlockedError(f"数据源拒绝访问，HTTP {response.status_code}", max(self.cooldown, wait))
                content_type = getattr(response, "headers", {}).get("Content-Type", "").lower()
                if "text/html" in content_type:
                    body = response.text[:16000].lower()
                    if any(marker in body for marker in ("captcha", "验证码", "安全验证", "访问验证", "access denied", "访问过于频繁")):
                        raise SourceBlockedError("数据源返回访问验证页面，停止采集")
                return response
            except Exception as exc:
                if is_rate_limit_error(exc):
                    wait = max(self.cooldown, getattr(exc, "retry_after_seconds", 0))
                    self.blocked_until = self.clock() + wait
                    raise SourceBlockedError(str(exc), wait) from exc
                raise
            finally:
                self.last_finished = self.clock()


_install_lock = threading.Lock()
_throttle: RequestThrottle | None = None


def install_akshare_request_guard(interval: float = 5) -> RequestThrottle:
    """只包装 AKShare 的 HTTP 入口，不修改 requests 或其他业务网络请求。"""
    global _throttle
    with _install_lock:
        if _throttle is not None:
            _throttle.interval = max(_throttle.interval, interval)
            return _throttle
        from akshare.utils import http
        from akshare.utils.context import config

        config.timeout = 20
        throttle = RequestThrottle(interval=max(3, interval))

        def wrap(function: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(function)
            def guarded(*args: Any, **kwargs: Any) -> Any:
                return throttle.call(function, *args, **kwargs)
            return guarded

        http.request = wrap(http.request)
        http.curl_request = wrap(http.curl_request)
        http.Session.request = wrap(http.Session.request)
        http.CurlSession.request = wrap(http.CurlSession.request)
        _throttle = throttle
        return throttle
