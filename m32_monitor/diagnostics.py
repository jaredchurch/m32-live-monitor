"""Structured diagnostics for the read-only M32 OSC transport."""
from collections import Counter, deque
import socket
import time

class OscDiagnostics:
    def __init__(self, console_host):
        self.console_host = console_host
        self.expected = set()
        self.cycle_received = set()
        self.last_received = {}
        self.counters = Counter()
        self.events = deque(maxlen=100)
        self.last_cycle_at = None
        self.cycle_started_at = None
        self.last_error = None

    def event(self, kind, message, address=None, detail=None):
        self.counters[kind] += 1
        item = {"time": time.time(), "kind": kind, "message": str(message), "address": address, "detail": detail}
        self.events.appendleft(item)
        self.last_error = item

    def begin_cycle(self, addresses):
        self.expected = set(addresses)
        self.cycle_received.clear()
        self.cycle_started_at = time.time()

    def received(self, address):
        self.cycle_received.add(address)
        self.last_received[address] = time.time()
        self.counters["valid_responses"] += 1

    def snapshot(self, online=False):
        now = time.time()
        missing = sorted(self.expected - self.cycle_received)
        stale = [{"address": a, "age_seconds": round(now - t, 1)} for a, t in sorted(self.last_received.items()) if now - t > 45]
        try:
            resolved = socket.gethostbyname(self.console_host)
        except OSError:
            resolved = None
        return {"online": online, "console_host": self.console_host, "resolved_host": resolved,
                "expected_count": len(self.expected), "received_count": len(self.cycle_received),
                "missing_count": len(missing), "missing": missing[:100], "stale_count": len(stale), "stale": stale[:100],
                "counters": dict(self.counters), "last_cycle_at": self.last_cycle_at,
                "cycle_started_at": self.cycle_started_at,
                "last_error": dict(self.last_error) if self.last_error else None,
                "events": [dict(x) for x in list(self.events)[:50]]}
