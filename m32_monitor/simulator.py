"""Instrumented UDP OSC simulator for M32-Edit and the live monitor.

The simulator deliberately logs every decoded inbound/outbound OSC message and
makes unsupported requests visible instead of silently dropping them.
"""
import asyncio
import logging
import socket
import struct
import time
from collections import Counter, deque

from pythonosc.osc_packet import OscPacket
from pythonosc.osc_message_builder import OscMessageBuilder

logger = logging.getLogger(__name__)


class Simulator:
    def __init__(self, state, host="0.0.0.0", port=10023, log_limit=3000,
                 name="M32-Live-Monitor", model="M32", firmware="4.06",
                 server_version="V2.07"):
        self.state, self.host, self.port = state, host, port
        self.name, self.model = name, model
        self.firmware, self.server_version = firmware, server_version
        self.transport = None
        self.clients = set()
        self.events = deque(maxlen=log_limit)
        self.counts = Counter()
        self.started_at = time.time()
        self.sequence = 0
        self.batch_subscriptions = {}
        self.subscription_tasks = {}

    async def start(self):
        loop = asyncio.get_running_loop()
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: SimulatorProtocol(self), local_addr=(self.host, self.port)
        )
        logger.info("M32 simulator listening on UDP %s:%s", self.host, self.port)

    async def stop(self):
        for task in tuple(self.subscription_tasks.values()):
            task.cancel()
        self.subscription_tasks.clear()
        self.batch_subscriptions.clear()
        if self.transport:
            self.transport.close()
            self.transport = None

    @staticmethod
    def _format_args(args):
        result = []
        for value in args:
            if isinstance(value, bytes):
                result.append({"type": "blob", "length": len(value), "hex": value[:24].hex()})
            else:
                result.append({"type": type(value).__name__, "value": repr(value)[:160]})
        return result

    def record(self, direction, outcome, address=None, args=(), peer=None, detail=None):
        self.sequence += 1
        event = {
            "sequence": self.sequence,
            "timestamp": time.time(),
            "direction": direction,
            "outcome": outcome,
            "address": address,
            "args": self._format_args(args),
            "peer": "%s:%s" % peer if peer else None,
            "detail": str(detail)[:500] if detail is not None else None,
        }
        self.events.append(event)
        self.counts[direction] += 1
        self.counts[outcome] += 1
        if outcome.startswith("unhandled") or outcome in ("malformed", "send_error"):
            logger.warning("OSC %s %s %s from/to %s: %s",
                           direction, outcome, address, event["peer"], event["detail"])
        else:
            logger.info("OSC %s %s %s from/to %s",
                        direction, outcome, address, event["peer"])
        return event

    def snapshot(self, limit=500, direction=None, outcome=None, search=None):
        events = list(self.events)
        if direction:
            events = [event for event in events if event["direction"] == direction]
        if outcome:
            events = [event for event in events if event["outcome"] == outcome]
        if search:
            needle = search.lower()
            events = [event for event in events if needle in
                      (str(event["address"]) + " " + str(event["detail"])).lower()]
        return {
            "mode": "simulator",
            "listening": self.transport is not None,
            "host": self.host,
            "port": self.port,
            "started_at": self.started_at,
            "clients": ["%s:%s" % client for client in sorted(self.clients)],
            "event_count": self.sequence,
            "retained_events": len(self.events),
            "counts": dict(self.counts),
            "events": events[-max(1, min(int(limit), 2000)):],
        }

    def clear_events(self):
        self.events.clear()
        self.counts.clear()
        self.sequence = 0

    def send(self, client, address, *values, outcome="response"):
        builder = OscMessageBuilder(address=address)
        for value in values:
            builder.add_arg(value)
        packet = builder.build().dgram
        try:
            if self.transport is None:
                raise RuntimeError("UDP transport is not running")
            self.transport.sendto(packet, client)
            self.record("out", outcome, address, values, client)
        except (OSError, RuntimeError) as exc:
            self.record("out", "send_error", address, values, client, exc)

    def handle(self, client, data):
        try:
            packet = OscPacket(data)
            messages = [timed.message for timed in packet.messages]
        except Exception as exc:
            self.record("in", "malformed", peer=client,
                        detail="%s; bytes=%s" % (exc, data[:48].hex()))
            return

        for message in messages:
            self._handle_message(client, message.address, message.params)

    def _local_ip(self, client):
        """Return the local interface address used to reach an OSC client."""
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(client)
            return probe.getsockname()[0]
        except OSError:
            return "127.0.0.1"
        finally:
            probe.close()

    @staticmethod
    def _meter_count(path):
        """Number of 32-bit meter values defined by the X32/M32 OSC protocol."""
        return {
            "/meters/0": 70, "/meters/1": 96, "/meters/2": 49,
            "/meters/3": 22, "/meters/4": 82, "/meters/5": 27,
            "/meters/6": 4, "/meters/7": 16, "/meters/8": 6,
            "/meters/9": 32, "/meters/10": 32, "/meters/11": 5,
            "/meters/12": 4, "/meters/13": 48, "/meters/14": 80,
            "/meters/15": 50, "/meters/16": 48,
        }.get(path)

    @staticmethod
    def _meter_blob(count):
        payload = struct.pack("<I", count) + struct.pack("<%df" % count, *([0.0] * count))
        return struct.pack(">I", len(payload)) + payload

    def _batch_response(self, client, subscription):
        blob = self._meter_blob(subscription["count"])
        self.send(client, subscription["alias_address"], blob,
                  outcome="batch_meter_response")

    async def _run_batch_subscription(self, key, subscription):
        interval = 0.05 * max(1, min(subscription["time_factor"], 99))
        try:
            while self.batch_subscriptions.get(key) is subscription:
                await asyncio.sleep(interval)
                if self.batch_subscriptions.get(key) is not subscription:
                    break
                if time.monotonic() >= subscription["expires_at"]:
                    break
                self._batch_response(key[0], subscription)
        except asyncio.CancelledError:
            raise
        finally:
            if self.batch_subscriptions.get(key) is subscription:
                self.batch_subscriptions.pop(key, None)
            if self.subscription_tasks.get(key) is asyncio.current_task():
                self.subscription_tasks.pop(key, None)

    def _handle_batchsubscribe(self, client, args):
        if (len(args) != 5 or not isinstance(args[0], str)
                or not isinstance(args[1], str)
                or any(type(value) is not int for value in args[2:])):
            self.record("in", "unhandled_command", "/batchsubscribe", args, client,
                        "Expected two strings followed by three integers")
            return
        alias, path, first, second, time_factor = args
        count = self._meter_count(path)
        if count is None:
            self.record("in", "unhandled_command", "/batchsubscribe", args, client,
                        "Unsupported meter path; expected /meters/0 through /meters/16")
            return
        if path == "/meters/5" and (first not in range(4) or second not in range(4)):
            self.record("in", "unhandled_command", "/batchsubscribe", args, client,
                        "/meters/5 channel and group meter IDs must be between 0 and 3")
            return
        if path == "/meters/6" and first not in range(72):
            self.record("in", "unhandled_command", "/batchsubscribe", args, client,
                        "/meters/6 channel ID must be between 0 and 71")
            return
        key = (client, alias)
        previous = self.subscription_tasks.pop(key, None)
        if previous:
            previous.cancel()
        subscription = {
            "alias": alias, "alias_address": alias if alias.startswith("/") else "/" + alias,
            "path": path, "first": first, "second": second, "count": count,
            "time_factor": max(1, min(time_factor, 99)),
            "expires_at": time.monotonic() + 10.0,
        }
        self.batch_subscriptions[key] = subscription
        self.record("in", "handled_batch_subscription", "/batchsubscribe", args, client,
                    "Meter subscription %s -> %s (%d values)" % (alias, path, count))
        self._batch_response(client, subscription)
        try:
            task = asyncio.get_running_loop().create_task(
                self._run_batch_subscription(key, subscription))
            self.subscription_tasks[key] = task
        except RuntimeError:
            pass

    def _handle_node(self, client, args):
        if len(args) != 1 or not isinstance(args[0], str):
            self.record("in", "unhandled_command", "/node", args, client,
                        "Expected exactly one X32node header string")
            return
        header = args[0].lstrip("/")
        if header == "-prefs/rta/visibility":
            value = self.state.get("/-prefs/rta/visibility")
            if value is None:
                value = 0
            response = "/-prefs/rta/visibility %d\\n" % int(value)
            self.send(client, "/node", response, outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned RTA visibility X32node")
            return
        self.record("in", "unhandled_command", "/node", args, client,
                    "No X32node response is defined for header %r" % header)

    def _handle_message(self, client, address, args):
        self.record("in", "received", address, args, client)

        if address in ("/xremote", "/subscribe"):
            self.clients.add(client)
            self.record("in", "handled_subscription", address, args, client,
                        "Client registered for unsolicited updates")
            return

        if address in ("/renew", "/unsubscribe"):
            if len(args) > 1 or (args and not isinstance(args[0], str)):
                self.record("in", "unhandled_command", address, args, client,
                            "Expected zero arguments or one subscription-name string")
                return
            name = args[0] if args else None
            matching = [key for key in self.batch_subscriptions
                        if key[0] == client and (name is None or
                        name in (key[1], key[1].lstrip("/")))]
            if address == "/renew":
                for key in matching:
                    self.batch_subscriptions[key]["expires_at"] = time.monotonic() + 10.0
            else:
                if not args:
                    self.clients.discard(client)
                    matching = [key for key in self.batch_subscriptions if key[0] == client]
                for key in matching:
                    self.batch_subscriptions.pop(key, None)
                    task = self.subscription_tasks.pop(key, None)
                    if task:
                        task.cancel()
            outcome = "handled_renewal" if address == "/renew" else "handled_unsubscription"
            self.record("in", outcome, address, args, client,
                        "Subscription maintenance request accepted (%d meter subscription(s) matched)" % len(matching))
            return

        if address == "/info":
            self.send(client, "/info", self.server_version, "osc-server", self.model,
                      self.firmware, outcome="identity_response")
            return
        if address == "/xinfo":
            self.send(client, "/xinfo", self._local_ip(client), self.name, self.model,
                      self.firmware, outcome="identity_response")
            return
        if address == "/status":
            self.send(client, "/status", "active", self._local_ip(client), self.name,
                      outcome="identity_response")
            return

        if address == "/batchsubscribe":
            self._handle_batchsubscribe(client, args)
            return
        if address == "/node":
            self._handle_node(client, args)
            return

        if args:
            if len(args) != 1:
                self.record("in", "unhandled_set", address, args, client,
                            "Only single-argument parameter SET messages are currently supported")
                return
            if self.state.update(address, args[0]):
                self.record("in", "handled_set", address, args, client)
                for subscriber in tuple(self.clients):
                    self.send(subscriber, address, args[0], outcome="subscription_update")
            else:
                self.record("in", "unhandled_set", address, args, client,
                            "No simulator state handler accepts this address/type")
            return

        value = self.state.get(address)
        if value is not None:
            self.record("in", "handled_get", address, args, client)
            self.send(client, address, value, outcome="get_response")
        else:
            self.record("in", "unhandled_get", address, args, client,
                        "No simulator state value or GET handler exists for this address")


class SimulatorProtocol(asyncio.DatagramProtocol):
    def __init__(self, simulator):
        self.simulator = simulator

    def connection_made(self, transport):
        self.simulator.transport = transport

    def datagram_received(self, data, addr):
        self.simulator.handle(addr, data)

    def error_received(self, exc):
        self.simulator.record("system", "transport_error", detail=exc)
