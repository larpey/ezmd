"""intomd_api.state: ephemeral shared state: sliding-window rate limits, gauges, fetch-node
heartbeats, and the per-job event buffer with pub/sub (docs/spec/part1.md sections 7.2, 7.3, 7.6).

`RedisState` is used with `INTOMD_QUEUE=rq` (and with fakeredis in tests). `MemoryState` serves the
single-process inline mode where no Redis exists.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol

EVENT_BUFFER_CAP = 500
EVENT_TTL_SECONDS = 7 * 24 * 3600
NODE_ONLINE_SECONDS = 60


@dataclass(frozen=True, slots=True)
class Event:
    id: int
    event: str
    data: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps({"id": self.id, "event": self.event, "data": self.data}, separators=(",", ":"))

    @staticmethod
    def from_json(raw: str | bytes) -> Event:
        obj = json.loads(raw)
        return Event(id=int(obj["id"]), event=str(obj["event"]), data=dict(obj["data"]))


@dataclass(frozen=True, slots=True)
class RateResult:
    allowed: bool
    limit: int
    remaining: int
    reset_epoch: int

    @property
    def retry_after(self) -> int:
        return max(1, self.reset_epoch - int(time.time()))


class Subscription(Protocol):
    def wait(self, timeout: float) -> bool: ...
    def close(self) -> None: ...


class StateBackend(Protocol):
    def ping(self) -> bool: ...
    def rate_hit(self, key: str, limit: int, window_s: int) -> RateResult: ...
    def gauge_incr(self, key: str, ttl_s: int) -> int: ...
    def gauge_decr(self, key: str) -> None: ...
    def node_heartbeat(self, node_id: str, info: dict[str, Any]) -> None: ...
    def nodes_online(self) -> list[str]: ...
    def append_event(self, job_id: str, event: str, data: dict[str, Any]) -> Event: ...
    def events_since(self, job_id: str, last_id: int) -> list[Event]: ...
    def subscribe(self, job_id: str) -> Subscription: ...
    def delete_job(self, job_id: str) -> None: ...


# ---------------------------------------------------------------------------
# In-memory (inline mode, single process)
# ---------------------------------------------------------------------------


class _MemorySubscription:
    def __init__(self, cond: threading.Condition, counter: dict[str, int], job_id: str) -> None:
        self._cond = cond
        self._counter = counter
        self._job_id = job_id
        self._seen = counter.get(job_id, 0)

    def wait(self, timeout: float) -> bool:
        with self._cond:
            if self._counter.get(self._job_id, 0) == self._seen:
                self._cond.wait(timeout)
            changed = self._counter.get(self._job_id, 0) != self._seen
            self._seen = self._counter.get(self._job_id, 0)
            return changed

    def close(self) -> None:
        return None


class MemoryState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._gauges: dict[str, int] = defaultdict(int)
        self._nodes: dict[str, float] = {}
        self._events: dict[str, list[Event]] = defaultdict(list)
        self._seq: dict[str, int] = defaultdict(int)

    def ping(self) -> bool:
        return True

    def rate_hit(self, key: str, limit: int, window_s: int) -> RateResult:
        now = time.time()
        with self._lock:
            hits = [t for t in self._windows[key] if t > now - window_s]
            allowed = len(hits) < limit
            if allowed:
                hits.append(now)
            self._windows[key] = hits
            reset = int((hits[0] if hits else now) + window_s) + 1
            return RateResult(allowed, limit, max(0, limit - len(hits)), reset)

    def gauge_incr(self, key: str, ttl_s: int) -> int:
        with self._lock:
            self._gauges[key] += 1
            return self._gauges[key]

    def gauge_decr(self, key: str) -> None:
        with self._lock:
            self._gauges[key] = max(0, self._gauges[key] - 1)

    def node_heartbeat(self, node_id: str, info: dict[str, Any]) -> None:
        with self._lock:
            self._nodes[node_id] = time.time()

    def nodes_online(self) -> list[str]:
        cutoff = time.time() - NODE_ONLINE_SECONDS
        with self._lock:
            return sorted(n for n, t in self._nodes.items() if t >= cutoff)

    def append_event(self, job_id: str, event: str, data: dict[str, Any]) -> Event:
        with self._cond:
            self._seq[job_id] += 1
            ev = Event(self._seq[job_id], event, data)
            buf = self._events[job_id]
            buf.append(ev)
            del buf[:-EVENT_BUFFER_CAP]
            self._cond.notify_all()
            return ev

    def events_since(self, job_id: str, last_id: int) -> list[Event]:
        with self._lock:
            return [e for e in self._events.get(job_id, []) if e.id > last_id]

    def subscribe(self, job_id: str) -> Subscription:
        with self._lock:
            return _MemorySubscription(self._cond, self._seq, job_id)

    def delete_job(self, job_id: str) -> None:
        with self._cond:
            self._events.pop(job_id, None)
            self._cond.notify_all()


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------


def channel(job_id: str) -> str:
    return f"intomd:job:{job_id}"


class _RedisSubscription:
    def __init__(self, redis: Any, job_id: str) -> None:
        self._pubsub = redis.pubsub(ignore_subscribe_messages=True)
        self._pubsub.subscribe(channel(job_id))

    def wait(self, timeout: float) -> bool:
        # get_message() returns None for swallowed subscribe confirmations too, so keep polling
        # until a real message arrives or the timeout is spent.
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            msg = self._pubsub.get_message(timeout=max(0.0, remaining))
            if msg is not None:
                while self._pubsub.get_message(timeout=0) is not None:
                    pass
                return True
            if remaining <= 0:
                return False

    def close(self) -> None:
        try:
            self._pubsub.close()
        except Exception:
            pass


class RedisState:
    def __init__(self, redis: Any) -> None:
        self.redis = redis

    def ping(self) -> bool:
        try:
            return bool(self.redis.ping())
        except Exception:
            return False

    def rate_hit(self, key: str, limit: int, window_s: int) -> RateResult:
        now = time.time()
        rkey = f"intomd:rl:{key}"
        member = f"{now:.6f}:{secrets.token_hex(4)}"
        pipe = self.redis.pipeline(transaction=True)
        pipe.zremrangebyscore(rkey, 0, now - window_s)
        pipe.zadd(rkey, {member: now})
        pipe.zcard(rkey)
        pipe.zrange(rkey, 0, 0, withscores=True)
        pipe.expire(rkey, window_s + 1)
        _, _, count, oldest, _ = pipe.execute()
        allowed = int(count) <= limit
        if not allowed:
            self.redis.zrem(rkey, member)
        oldest_ts = float(oldest[0][1]) if oldest else now
        used = min(int(count), limit)
        return RateResult(allowed, limit, max(0, limit - used), int(oldest_ts + window_s) + 1)

    def gauge_incr(self, key: str, ttl_s: int) -> int:
        rkey = f"intomd:gauge:{key}"
        pipe = self.redis.pipeline(transaction=True)
        pipe.incr(rkey)
        pipe.expire(rkey, ttl_s)
        value, _ = pipe.execute()
        return int(value)

    def gauge_decr(self, key: str) -> None:
        rkey = f"intomd:gauge:{key}"
        if int(self.redis.decr(rkey)) < 0:
            self.redis.set(rkey, 0)

    def node_heartbeat(self, node_id: str, info: dict[str, Any]) -> None:
        pipe = self.redis.pipeline(transaction=True)
        pipe.zadd("intomd:fetchnodes", {node_id: time.time()})
        pipe.set(f"intomd:fetchnode:{node_id}", json.dumps(info), ex=NODE_ONLINE_SECONDS * 10)
        pipe.execute()

    def nodes_online(self) -> list[str]:
        cutoff = time.time() - NODE_ONLINE_SECONDS
        self.redis.zremrangebyscore("intomd:fetchnodes", 0, cutoff - 3600)
        raw = self.redis.zrangebyscore("intomd:fetchnodes", cutoff, "+inf")
        return sorted(r.decode() if isinstance(r, bytes) else str(r) for r in raw)

    def append_event(self, job_id: str, event: str, data: dict[str, Any]) -> Event:
        seq = int(self.redis.incr(f"intomd:job:{job_id}:seq"))
        ev = Event(seq, event, data)
        raw = ev.to_json()
        key = f"intomd:job:{job_id}:events"
        pipe = self.redis.pipeline(transaction=True)
        pipe.rpush(key, raw)
        pipe.ltrim(key, -EVENT_BUFFER_CAP, -1)
        pipe.expire(key, EVENT_TTL_SECONDS)
        pipe.expire(f"intomd:job:{job_id}:seq", EVENT_TTL_SECONDS)
        pipe.publish(channel(job_id), raw)
        pipe.execute()
        return ev

    def events_since(self, job_id: str, last_id: int) -> list[Event]:
        raw = self.redis.lrange(f"intomd:job:{job_id}:events", 0, -1)
        return [e for e in (Event.from_json(r) for r in raw) if e.id > last_id]

    def subscribe(self, job_id: str) -> Subscription:
        return _RedisSubscription(self.redis, job_id)

    def delete_job(self, job_id: str) -> None:
        self.redis.delete(f"intomd:job:{job_id}:events", f"intomd:job:{job_id}:seq")
