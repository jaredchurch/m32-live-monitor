"""Instrumented UDP OSC simulator for M32-Edit and the live monitor.

The simulator deliberately logs every decoded inbound/outbound OSC message and
makes unsupported requests visible instead of silently dropping them.
"""
import asyncio
import logging
import socket
import math
import json
import shlex
import struct
import time
from collections import Counter, deque

from pythonosc.osc_packet import OscPacket
from pythonosc.osc_message_builder import OscMessageBuilder

logger = logging.getLogger(__name__)


TYPE_NAMES_FX_1_4 = ("HALL", "AMBI", "RPLT", "ROOM", "CHAM", "PLAT", "VREV", "VRM",
    "GATE", "RVRS", "DLY", "3TAP", "4TAP", "CRS", "FLNG", "PHAS", "DIMC", "FILT",
    "ROTA", "PAN", "SUB", "D/RV", "CR/R", "FL/R", "D/CR", "D/FL", "MODD", "GEQ2",
    "GEQ", "TEQ2", "TEQ", "DES2", "DES", "P1A", "P1A2", "PQ5", "PQ5S", "WAVD",
    "LIM", "CMB", "CMB2", "FAC", "FAC1M", "FAC2", "LEC", "LEC2", "ULC", "ULC2",
    "ENH2", "ENH", "EXC2", "EXC", "IMG", "EDI", "SON", "AMP2", "AMP", "DRV2",
    "DRV", "PIT2", "PIT")
TYPE_NAMES_FX_5_8 = ("GEQ2", "GEQ", "TEQ2", "TEQ", "DES2", "DES", "P1A", "P1A2",
    "PQ5", "PQ5S", "WAVD", "LIM", "FAC", "FAC1M", "FAC2", "LEC", "LEC2", "ULC",
    "ULC2", "ENH2", "ENH", "EXC2", "EXC", "IMG", "EDI", "SON", "AMP2", "AMP",
    "DRV2", "DRV", "PHAS", "FILT", "PAN", "SUB")


class Simulator:
    def __init__(self, state, host="0.0.0.0", port=10023, log_limit=3000,
                 name="M32-Simulation", model="M32", firmware="4.06",
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
        self.format_subscriptions = {}
        self.format_tasks = {}

    async def start(self):
        loop = asyncio.get_running_loop()
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: SimulatorProtocol(self), local_addr=(self.host, self.port)
        )
        logger.info("M32 simulator listening on UDP %s:%s", self.host, self.port)

    async def stop(self):
        for task in tuple(self.subscription_tasks.values()):
            task.cancel()
        for task in tuple(self.format_tasks.values()):
            task.cancel()
        self.format_tasks.clear()
        self.subscription_tasks.clear()
        self.batch_subscriptions.clear()
        self.format_subscriptions.clear()
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

    def snapshot(self, limit=500, direction=None, outcome=None, search=None, exceptions_only=False):
        events = list(self.events)
        if direction:
            events = [event for event in events if event["direction"] == direction]
        if outcome:
            events = [event for event in events if event["outcome"] == outcome]
        if exceptions_only:
            events = [event for event in events if event["outcome"].startswith("unhandled") or
                      event["outcome"] in ("malformed", "send_error")]
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

    
    @staticmethod
    def _format_interval(time_factor):
        if time_factor <= 0:
            return 0.05
        return min(10.0 / 3.0, max(0.05, time_factor / 20.0))

    @staticmethod
    def _expand_format_pattern(pattern, first, last):
        if "**" in pattern:
            if first == 0 and last == 0 and "/solosw/**" in pattern:
                first, last = 1, 80
            if first > 0 and last >= first:
                return [pattern.replace("**", "%02d" % number)
                        for number in range(first, last + 1)]
        elif "*" in pattern and first > 0 and last >= first:
            return [pattern.replace("*", str(number))
                    for number in range(first, last + 1)]
        return [pattern]

    def _format_blob(self, subscription):
        string_paths = {
            "/-usb/path", "/-usb/path/", "/-usb/title",
            "/-stat/aes50/A", "/-stat/aes50/B",
        }
        body = bytearray()
        for pattern in subscription["patterns"]:
            for address in self._expand_format_pattern(
                    pattern, subscription["first"], subscription["last"]):
                value = self.state.get(address)
                if address in string_paths:
                    encoded = str(value or "").encode("utf-8")[:32]
                    body.extend(encoded.ljust(32, b"\x00"))
                else:
                    body.extend(struct.pack("<i", int(value or 0)))
        return struct.pack("<I", len(body)) + bytes(body)

    def _format_response(self, client, subscription):
        blob = self._format_blob(subscription)
        alias = subscription["alias"]
        self.send(client, alias if alias.startswith("/") else "/" + alias,
                  blob, outcome="format_subscription_response")

    async def _run_format_subscription(self, key, subscription):
        try:
            while self.format_subscriptions.get(key) is subscription:
                await asyncio.sleep(self._format_interval(subscription["time_factor"]))
                if self.format_subscriptions.get(key) is not subscription:
                    break
                if time.monotonic() >= subscription["expires_at"]:
                    break
                self._format_response(key[0], subscription)
        except asyncio.CancelledError:
            raise
        finally:
            if self.format_subscriptions.get(key) is subscription:
                self.format_subscriptions.pop(key, None)
            if self.format_tasks.get(key) is asyncio.current_task():
                self.format_tasks.pop(key, None)

    def _handle_formatsubscribe(self, client, args):
        groups = []
        index = 0
        while index < len(args):
            if not isinstance(args[index], str):
                self.record("in", "unhandled_command", "/formatsubscribe", args, client,
                            "Expected an alias string at the start of each subscription group")
                return
            alias = args[index]
            index += 1
            patterns = []
            while index < len(args) and isinstance(args[index], str):
                patterns.append(args[index])
                index += 1
            if not patterns or index + 3 > len(args) or any(type(v) is not int for v in args[index:index + 3]):
                self.record("in", "unhandled_command", "/formatsubscribe", args, client,
                            "Each group requires one or more address strings followed by three integers")
                return
            first, last, time_factor = args[index:index + 3]
            index += 3
            if first < 0 or last < 0 or ((first == 0) != (last == 0)) or (last and first > last) or not 0 <= time_factor <= 99:
                self.record("in", "unhandled_command", "/formatsubscribe", args, client,
                            "Invalid wildcard range or time factor")
                return
            groups.append({"alias": alias, "patterns": patterns, "first": first,
                           "last": last, "time_factor": time_factor,
                           "expires_at": time.monotonic() + 10.0})
        for group in groups:
            key = (client, group["alias"])
            previous = self.format_tasks.pop(key, None)
            if previous:
                previous.cancel()
            self.format_subscriptions[key] = group
            self._format_response(client, group)
            try:
                task = asyncio.get_running_loop().create_task(
                    self._run_format_subscription(key, group))
                self.format_tasks[key] = task
            except RuntimeError:
                pass
        self.record("in", "handled_format_subscription", "/formatsubscribe", args, client,
                    "Registered %d formatted subscription group(s)" % len(groups))

    @staticmethod
    def _rta_node_value(header, value):
        """Format a single RTA X32node field using the console's text enum conventions."""
        enums = {
            "-prefs/rta/visibility": ("OFF", "25%", "30%", "35%", "40%", "45%", "50%", "55%", "60%", "65%", "70%", "75%", "80%"),
            "-prefs/rta/autogain": ("OFF", "ON"),
            "-prefs/rta/pos": ("PRE", "POST"),
            "-prefs/rta/mode": ("BAR", "SPEC"),
            "-prefs/rta/det": ("RMS", "PEAK"),
            "-prefs/rta/peakhold": ("OFF", "1", "2", "3", "4", "5", "6", "7", "8"),
            "-stat/rtamodeeq": ("BAR", "SPEC"),
            "-stat/rtamodegeq": ("BAR", "SPEC"),
            "-stat/rtaeqpre": ("OFF", "ON"),
            "-stat/rtageqpost": ("OFF", "ON"),
        }
        if header in enums:
            index = int(value)
            return enums[header][index]
        if header in ("-prefs/rta/options", "-prefs/rta/option"):
            return "%" + format(int(value), "06b")
        if header == "-prefs/rta/gain":
            return "%.6f" % float(value)
        if header == "-prefs/rta/decay":
            return "%.6f" % float(value)
        return str(int(value))

    def _rta_node_group(self):
        """Build the documented ten-field /-prefs/rta node payload."""
        p = self.state.preferences
        visibility = ("OFF", "25%", "30%", "35%", "40%", "45%", "50%", "55%",
                      "60%", "65%", "70%", "75%", "80%")[int(p["rta/visibility"])]
        gain = "%.0f" % (float(p["rta/gain"]) * 60.0)
        autogain = ("OFF", "ON")[int(p["rta/autogain"])]
        source = str(int(p["rta/source"]))
        pos = ("PRE", "POST")[int(p["rta/pos"])]
        mode = ("BAR", "SPEC")[int(p["rta/mode"])]
        options = "%" + format(int(p["rta/options"]), "06b")
        detector = ("RMS", "PEAK")[int(p["rta/det"])]
        decay = "%.2f" % (0.25 * math.exp(float(p["rta/decay"]) * math.log(16.0 / 0.25)))
        peakhold = ("OFF", "1", "2", "3", "4", "5", "6", "7", "8")[int(p["rta/peakhold"])]
        return "/-prefs/rta %s %s %s %s %s %s %s %s %s %s\n" % (
            visibility, gain, autogain, source, pos, mode, options, detector, decay, peakhold)

    def _handle_node_set(self, client, args):
        """Apply X32node text writes for the RTA preference group and individual fields."""
        if len(args) != 1 or not isinstance(args[0], str):
            self.record("in", "unhandled_set", "/", args, client,
                        "Expected one X32node text string")
            return
        try:
            tokens = shlex.split(args[0])
            if not tokens:
                raise ValueError("Empty X32node text")
            header = tokens[0].lstrip("/")
            values = tokens[1:]
            if header.startswith(("config/userrout/out/", "config/userrout/in/")) and len(values) == 1:
                address = "/" + header
                parsed = [int(values[0], 0)]
                paths = [address]
            elif header.startswith("config/userctrl/"):
                parts = header.split("/")
                bank = parts[2]
                if bank not in ("A", "B", "C"):
                    raise ValueError("Unknown user control bank")
                colors = ("OFF", "RD", "GN", "YE", "BL", "MG", "CY", "WH",
                          "OFFi", "RDi", "GNi", "YEi", "BLi", "MGi", "CYi", "WHi")
                if len(parts) == 3:
                    if len(values) != 13:
                        raise ValueError("User control bank requires colour, four encoders and eight buttons")
                    parsed = [colors.index(values[0])] + values[1:]
                    paths = ["/config/userctrl/%s/color" % bank]
                    paths += ["/config/userctrl/%s/enc/%d" % (bank, n) for n in range(1, 5)]
                    paths += ["/config/userctrl/%s/btn/%d" % (bank, n) for n in range(5, 13)]
                elif len(parts) == 4 and parts[3] in ("enc", "btn"):
                    section = parts[3]
                    expected = 4 if section == "enc" else 8
                    if len(values) != expected:
                        raise ValueError("User control %s node requires %d strings" % (section, expected))
                    slots = range(1, 5) if section == "enc" else range(5, 13)
                    paths = ["/config/userctrl/%s/%s/%d" % (bank, section, n) for n in slots]
                    parsed = values
                elif len(parts) == 4 and parts[3] == "color" and len(values) == 1:
                    paths, parsed = ["/" + header], [colors.index(values[0])]
                elif len(parts) == 5 and parts[3] in ("enc", "btn") and len(values) == 1:
                    paths, parsed = ["/" + header], values
                else:
                    raise ValueError("Unsupported user control node")
            elif header == "config/tape":
                if len(values) != 3:
                    raise ValueError("Tape node requires gainL, gainR and autoplay")
                paths = ["/config/tape/gainL", "/config/tape/gainR", "/config/tape/autoplay"]
                parsed = [float(values[0]), float(values[1]), ("OFF", "ON").index(values[2])]
            elif header.startswith("config/tape/") and len(values) == 1:
                field = header.rsplit("/", 1)[1]
                parsed = [("OFF", "ON").index(values[0])] if field == "autoplay" else [float(values[0])]
                paths = ["/" + header]
            elif header == "config/amixenable":
                if len(values) != 2:
                    raise ValueError("Automix enable node requires X and Y states")
                paths = ["/config/amixenable/X", "/config/amixenable/Y"]
                parsed = [("OFF", "ON").index(v) for v in values]
            elif header.startswith("config/amixenable/") and len(values) == 1:
                paths, parsed = ["/" + header], [("OFF", "ON").index(values[0])]
            elif header == "config/dp48":
                if len(values) != 3:
                    raise ValueError("DP48 node requires scope bitmap, broadcast and AES50 target")
                scope = values[0]
                parsed = [int(scope[1:], 2) if scope.startswith("%") else int(scope, 0),
                          int(values[1], 0), ("AESA", "AESB").index(values[2])]
                paths = ["/config/dp48/scope", "/config/dp48/broadcast", "/config/dp48/aesAB"]
            elif header in ("config/dp48/link", "config/dp48/assign", "config/dp48/grpname"):
                section = header.rsplit("/", 1)[1]
                slots = {"link": range(1, 25), "assign": range(1, 49), "grpname": range(1, 13)}[section]
                if len(values) != len(slots):
                    raise ValueError("DP48 %s node requires %d values" % (section, len(slots)))
                paths = ["/config/dp48/%s/%02d" % (section, n) for n in slots]
                parsed = values if section == "grpname" else [int(v, 0) for v in values]
            elif header.startswith("config/dp48/") and len(values) == 1:
                parts = header.split("/")
                if len(parts) == 3:
                    field = parts[2]
                    if field == "scope":
                        token = values[0]
                        parsed = [int(token[1:], 2) if token.startswith("%") else int(token, 0)]
                    elif field == "aesAB":
                        parsed = [("AESA", "AESB").index(values[0])]
                    else:
                        parsed = [int(values[0], 0)]
                else:
                    parsed = [values[0] if parts[2] == "grpname" else int(values[0], 0)]
                paths = ["/" + header]
            elif header == "config/osc":
                if len(values) != 6:
                    raise ValueError("Oscillator group requires level, F1, F2, selected frequency, type and destination")
                parsed = [float(values[0]), float(values[1]), float(values[2]),
                          ("F1", "F2").index(values[3]),
                          ("SINE", "PINK", "WHITE").index(values[4]), int(values[5], 0)]
                paths = ["/config/osc/" + field for field in ("level", "f1", "f2", "fsel", "type", "dest")]
            elif header == "config/talk":
                if len(values) != 2:
                    raise ValueError("Talkback group requires enable and source")
                parsed = [("OFF", "ON").index(values[0]), ("INT", "EXT").index(values[1])]
                paths = ["/config/talk/enable", "/config/talk/source"]
            elif header in ("config/talk/A", "config/talk/B"):
                if len(values) != 4:
                    raise ValueError("Talkback A/B group requires level, dim, latch and destination map")
                section = header.rsplit("/", 1)[1]
                dest = values[3]
                dest_value = int(dest[1:], 2) if dest.startswith("%") else int(dest, 0)
                parsed = [float(values[0]), ("OFF", "ON").index(values[1]),
                          ("OFF", "ON").index(values[2]), dest_value]
                paths = ["/config/talk/%s/%s" % (section, field)
                         for field in ("level", "dim", "latch", "destmap")]
            elif header.startswith("config/talk/") and len(values) == 1:
                field = header.rsplit("/", 1)[1]
                if field in ("enable", "dim", "latch"):
                    parsed = [("OFF", "ON").index(values[0])]
                elif field == "source":
                    parsed = [("INT", "EXT").index(values[0])]
                elif field == "destmap":
                    token = values[0]
                    parsed = [int(token[1:], 2) if token.startswith("%") else int(token, 0)]
                elif field == "level":
                    parsed = [float(values[0])]
                else:
                    raise ValueError("Unknown talkback field")
                paths = ["/" + header]
            elif header.startswith("config/osc/") and len(values) == 1:
                field = header.rsplit("/", 1)[1]
                path = "/" + header
                if field in ("fsel",):
                    parsed = [("F1", "F2").index(values[0])]
                elif field == "type":
                    parsed = [("SINE", "PINK", "WHITE").index(values[0])]
                elif field in ("level", "f1", "f2"):
                    parsed = [float(values[0])]
                elif field == "dest":
                    parsed = [int(values[0], 0)]
                else:
                    raise ValueError("Unknown oscillator field")
                paths = [path]
            elif header == "-prefs/rta":
                if len(values) != 10:
                    raise ValueError("RTA group requires 10 ordered values")
                paths = ["/-prefs/rta/" + key for key in (
                    "visibility", "gain", "autogain", "source", "pos", "mode",
                    "options", "det", "decay", "peakhold")]
                parsed = [
                    int(("OFF", "25%", "30%", "35%", "40%", "45%", "50%", "55%", "60%", "65%", "70%", "75%", "80%").index(values[0])),
                    float(values[1]) / 60.0,
                    ("OFF", "ON").index(values[2]),
                    int(values[3]),
                    ("PRE", "POST").index(values[4]),
                    ("BAR", "SPEC").index(values[5]),
                    int(values[6].lstrip("%"), 2),
                    ("RMS", "PEAK").index(values[7]),
                    math.log(float(values[8]) / 0.25) / math.log(16.0 / 0.25),
                    ("OFF", "1", "2", "3", "4", "5", "6", "7", "8").index(values[9]),
                ]
            elif header.startswith("-prefs/rta/") and len(values) == 1:
                key = header.rsplit("/", 1)[-1]
                path = "/" + header
                enum_values = {
                    "visibility": ("OFF", "25%", "30%", "35%", "40%", "45%", "50%", "55%", "60%", "65%", "70%", "75%", "80%"),
                    "autogain": ("OFF", "ON"), "pos": ("PRE", "POST"),
                    "mode": ("BAR", "SPEC"), "det": ("RMS", "PEAK"),
                    "peakhold": ("OFF", "1", "2", "3", "4", "5", "6", "7", "8"),
                }
                if key in enum_values:
                    parsed = [enum_values[key].index(values[0])]
                elif key == "gain":
                    parsed = [float(values[0]) / 60.0]
                elif key == "decay":
                    parsed = [math.log(float(values[0]) / 0.25) / math.log(16.0 / 0.25)]
                elif key == "source":
                    parsed = [int(values[0])]
                elif key in ("options", "option"):
                    parsed = [int(values[0].lstrip("%"), 2) if values[0].startswith("%") else int(values[0], 0)]
                else:
                    raise ValueError("Unknown RTA preference")
                paths, parsed = [path], parsed
            elif header.startswith(("outputs/main/", "outputs/aux/", "outputs/p16/", "outputs/aes/", "outputs/rec/")):
                parts = header.split("/")
                family = parts[1]
                collection = {"main": self.state.output_main, "aux": self.state.output_aux, "p16": self.state.output_p16, "aes": self.state.output_aes, "rec": self.state.output_rec}[family]
                if len(parts) not in (3, 4, 5) or not parts[2].isdigit() or int(parts[2]) not in collection:
                    raise ValueError("Unknown physical %s output" % family)
                number = int(parts[2])
                prefix = "/outputs/%s/%02d" % (family, number)
                positions = ("IN/LC", "IN/LC+M", "<-EQ", "<-EQ+M", "EQ->", "EQ->+M", "PRE", "PRE+M", "POST")
                speakers = ("none", "iQ8", "iQ10", "iQ12", "iQ15", "iQ15B", "iQ18B")
                if len(parts) == 3:
                    expected = 2 if family in ("p16", "rec") else 3
                    if len(values) != expected: raise ValueError("Output node requires %d values" % expected)
                    paths = [prefix + "/src", prefix + "/pos"]
                    parsed = [int(values[0], 0), positions.index(values[1])]
                    if family in ("main", "aux", "aes"):
                        paths.append(prefix + "/invert")
                        parsed.append(("OFF", "ON").index(values[2]))
                elif family == "p16" and parts[3] == "iQ" and len(parts) == 4:
                    if len(values) != 2: raise ValueError("P16 iQ node requires group and speaker")
                    paths = [prefix + "/iQ/group", prefix + "/iQ/speaker"]
                    parsed = [("OFF", "A", "B").index(values[0]), speakers.index(values[1])]
                elif family == "p16" and len(parts) == 5 and parts[3:5] == ["iQ", "group"] and len(values) == 1:
                    paths, parsed = [prefix + "/iQ/group"], [("OFF", "A", "B").index(values[0])]
                elif family == "p16" and len(parts) == 5 and parts[3:5] == ["iQ", "speaker"] and len(values) == 1:
                    paths, parsed = [prefix + "/iQ/speaker"], [speakers.index(values[0])]
                elif family == "main" and parts[3] == "delay" and len(parts) == 4:
                    if len(values) != 2: raise ValueError("Main output delay node requires enable and time")
                    paths = [prefix + "/delay/on", prefix + "/delay/time"]
                    parsed = [("OFF", "ON").index(values[0]), float(values[1])]
                elif family == "main" and len(parts) == 5 and parts[3:5] == ["delay", "on"] and len(values) == 1:
                    paths, parsed = [prefix + "/delay/on"], [("OFF", "ON").index(values[0])]
                elif family == "main" and len(parts) == 5 and parts[3:5] == ["delay", "time"] and len(values) == 1:
                    paths, parsed = [prefix + "/delay/time"], [float(values[0])]
                elif len(parts) == 4 and parts[3] in ("src", "pos", "invert") and (parts[3] != "invert" or family in ("main", "aux", "aes")) and len(values) == 1:
                    field = parts[3]
                    if field == "src": parsed = [int(values[0], 0)]
                    elif field == "pos": parsed = [positions.index(values[0])]
                    else: parsed = [("OFF", "ON").index(values[0])]
                    paths = [prefix + "/" + field]
                else:
                    raise ValueError("Unsupported physical %s output node" % family)
                previous = dict(collection[number])
                if not all(self.state.update(path, value) for path, value in zip(paths, parsed)):
                    collection[number].update(previous)
                    raise ValueError("Invalid physical %s output value" % family)
            elif header.startswith("fx/"):
                parts = header.split("/")
                if len(parts) not in (2, 3, 4) or not parts[1].isdigit() or int(parts[1]) not in self.state.fx:
                    raise ValueError("Unknown FX slot")
                number = int(parts[1])
                type_names = TYPE_NAMES_FX_1_4 if number <= 4 else TYPE_NAMES_FX_5_8
                if len(parts) == 2 or (len(parts) == 3 and parts[2] == "type"):
                    if len(values) != 1:
                        raise ValueError("FX type node requires one effect type")
                    paths = ["/fx/%02d/type" % number]
                    parsed = [type_names.index(values[0])]
                elif len(parts) == 3 and parts[2] == "source":
                    if number > 4 or len(values) != 2:
                        raise ValueError("FX source node is only available on slots 1-4 and requires L/R sources")
                    source_names = ("INS",) + tuple("MIX%d" % n for n in range(1, 17)) + ("M/C",)
                    paths = ["/fx/%02d/source/l" % number, "/fx/%02d/source/r" % number]
                    parsed = [source_names.index(values[0]), source_names.index(values[1])]
                elif len(parts) == 3 and parts[2] == "par":
                    if len(values) != 64:
                        raise ValueError("FX parameter node requires 64 values")
                    paths = ["/fx/%02d/par/%02d" % (number, n) for n in range(1, 65)]
                    parsed = [float(value) for value in values]
                elif len(parts) == 4 and parts[2] == "par" and parts[3].isdigit() and len(values) == 1:
                    parameter = int(parts[3])
                    if not 1 <= parameter <= 64:
                        raise ValueError("FX parameter index must be 01-64")
                    paths = ["/fx/%02d/par/%02d" % (number, parameter)]
                    parsed = [float(values[0])]
                elif len(parts) == 4 and parts[2] == "source" and parts[3] in ("l", "r") and len(values) == 1:
                    if number > 4:
                        raise ValueError("FX source is only available on slots 1-4")
                    source_names = ("INS",) + tuple("MIX%d" % n for n in range(1, 17)) + ("M/C",)
                    paths = ["/fx/%02d/source/%s" % (number, parts[3])]
                    parsed = [source_names.index(values[0])]
                else:
                    raise ValueError("Unsupported FX node")
                if not all(math.isfinite(float(value)) for value in parsed if isinstance(value, (int, float))):
                    raise ValueError("FX values must be finite")
            elif header.startswith("dca/"):
                parts = header.split("/")
                if len(parts) not in (2, 3) or not parts[1].isdigit() or int(parts[1]) not in self.state.dcas:
                    raise ValueError("Unknown DCA node")
                number = int(parts[1])
                if len(parts) == 2:
                    if len(values) != 5:
                        raise ValueError("DCA node requires on, fader, name, icon and colour")
                    paths = ["/dca/%d/on" % number, "/dca/%d/fader" % number,
                             "/dca/%d/config/name" % number, "/dca/%d/config/icon" % number,
                             "/dca/%d/config/color" % number]
                    parsed = [("OFF", "ON").index(values[0]), float(values[1]), values[2],
                              int(values[3], 0), ("OFF", "RD", "GN", "YE", "BL", "MG", "CY", "WH",
                              "OFFi", "RDi", "GNi", "YEi", "BLi", "MGi", "CYi", "WHi").index(values[4])]
                else:
                    if parts[2] != "config" or len(values) != 3:
                        raise ValueError("DCA config node requires name, icon and colour")
                    paths = ["/dca/%d/config/name" % number, "/dca/%d/config/icon" % number,
                             "/dca/%d/config/color" % number]
                    parsed = [values[0], int(values[1], 0),
                              ("OFF", "RD", "GN", "YE", "BL", "MG", "CY", "WH",
                               "OFFi", "RDi", "GNi", "YEi", "BLi", "MGi", "CYi", "WHi").index(values[2])]
                if len(parts) == 2:
                    valid = (parsed[0] in (0, 1) and 0.0 <= parsed[1] <= 1.0
                             and len(parsed[2]) <= 12 and 1 <= parsed[3] <= 74
                             and 0 <= parsed[4] <= 15)
                else:
                    valid = (len(parsed[0]) <= 12 and 1 <= parsed[1] <= 74
                             and 0 <= parsed[2] <= 15)
                if not valid:
                    raise ValueError("Invalid DCA node values")
                for path, value in zip(paths, parsed):
                    if not self.state.update(path, value):
                        raise ValueError("Invalid DCA node value for %s" % path)
            elif self._strip_node_header(header) is not None:
                prefix, node, fields = self._strip_node_header(header)
                if len(values) != len(fields):
                    raise ValueError("Strip node %s requires %d values" % (header, len(fields)))
                paths = [prefix + "/" + node + "/" + field for field in fields]
                schema = self.state.main_node_schema if prefix in ("/main/st", "/main/m") else self.state.strip_node_schema[header.split("/")[0]]
                parsed = [self._parse_strip_node_value(schema[node][field], token)
                          for field, token in zip(fields, values)]
                for path, value in zip(paths, parsed):
                    valid = (self.state._valid_main_node_value(path, value)
                             if path.startswith(("/main/st/", "/main/m/"))
                             else self.state._valid_strip_node_value(path, value))
                    if not valid:
                        raise ValueError("Invalid value for %s: %r" % (path, value))
            else:
                raise ValueError("Unsupported X32node SET header %r" % header)
            old_preferences = dict(self.state.preferences)
            old_talk = json.loads(json.dumps(self.state.talk_config))
            old_osc = dict(self.state.osc_config)
            old_status = dict(self.state.rta_status)
            old_user_controls = json.loads(json.dumps(self.state.user_controls))
            old_tape = dict(self.state.tape_config)
            old_amix = dict(self.state.amix_enable)
            old_dp48 = json.loads(json.dumps(self.state.dp48_config))
            old_received = set(self.state.received)
            for path, value in zip(paths, parsed):
                if not self.state.update(path, value):
                    self.state.preferences.update(old_preferences)
                    self.state.talk_config = old_talk
                    self.state.osc_config.update(old_osc)
                    self.state.rta_status.update(old_status)
                    self.state.user_controls = old_user_controls
                    self.state.tape_config = old_tape
                    self.state.amix_enable = old_amix
                    self.state.dp48_config = old_dp48
                    self.state.received.clear()
                    self.state.received.update(old_received)
                    raise ValueError("Invalid value for %s: %r" % (path, value))
        except (ValueError, IndexError, ZeroDivisionError) as exc:
            self.record("in", "unhandled_set", "/", args, client, str(exc))
            return
        self.record("in", "handled_node_set", "/", args, client,
                    "Applied %d %s configuration value(s)" % (
                        len(paths), "talkback" if paths[0].startswith("/config/talk/") else "oscillator" if paths[0].startswith("/config/osc/") else "user routing" if paths[0].startswith("/config/userrout/") else "RTA preference"))
        self.send(client, "/", args[0], outcome="node_set_echo")
        for subscriber in tuple(self.clients):
            self.send(subscriber, "/", args[0], outcome="subscription_update")

    def _urec_node_group(self):
        """Return the scalar X-Live recorder status node in documented field order."""
        values = self.state.urec
        fields = (
            "sessionmax", "markermax", "sessionlen", "sessionpos", "markerpos",
            "batterystate", "srate", "tracks", "sessionspan", "sessionoffs",
            "sd1state", "sd2state", "sd1info", "sd2info", "errormessage", "errorcode",
        )
        enums = {
            "batterystate": ("NONE", "GOOD", "LOW"),
            "sd1state": ("NONE", "READY", "PROTECT", "ERROR"),
            "sd2state": ("NONE", "READY", "PROTECT", "ERROR"),
        }
        rendered = []
        for field in fields:
            value = values[field]
            if field in enums:
                value = enums[field][int(value)]
            elif field in ("sd1info", "sd2info", "errormessage"):
                value = json.dumps(value, ensure_ascii=False)
            else:
                value = str(int(value))
            rendered.append(value)
        return "/-urec " + " ".join(rendered) + "\n"

    def _config_link_node_group(self, family):
        """Render a complete stereo-link configuration node."""
        links = self.state.config_links[family]
        return "".join("/config/%s/%s %s\n" % (
            family, pair, "ON" if enabled else "OFF")
            for pair, enabled in links.items())


    def _config_linkcfg_node_group(self):
        """Render linked-channel parameter coupling flags in protocol order."""
        fields = ("hadly", "eq", "dyn", "fdrmute")
        values = " ".join("ON" if self.state.link_config[field] else "OFF"
                          for field in fields)
        return "/config/linkcfg " + values + "\n"

    def _config_mono_node_group(self):
        """Render mono/centre output mode and Main L/R link settings."""
        mode = ("LR+M", "LCR")[int(self.state.mono_config["mode"])]
        link = ("OFF", "ON")[int(self.state.mono_config["link"])]
        return "/config/mono/mode %s\n/config/mono/link %s\n" % (mode, link)

    def _config_solo_node_group(self):
        """Render the 17-field solo-monitor configuration node."""
        values = self.state.solo_config
        source = ("OFF", "LR", "LR+C", "LRPFL", "LRAFL", "AUX56", "AUX78")[int(values["source"])]
        pfl_afl = lambda field: ("PFL", "AFL")[int(values[field])]
        on_off = lambda field: ("OFF", "ON")[int(values[field])]
        ordered = (
            "%.1f" % values["level"], source, "%.1f" % values["sourcetrim"],
            pfl_afl("chmode"), pfl_afl("busmode"), pfl_afl("dcamode"),
            on_off("exclusive"), on_off("followsel"), on_off("followsolo"),
            "%.1f" % values["dimatt"], on_off("dim"), on_off("mono"),
            on_off("delay"), "%.1f" % values["delaytime"],
            on_off("masterctrl"), on_off("mute"), on_off("dimpfl"),
        )
        return "/config/solo " + " ".join(ordered) + "\n"

    def _config_talk_node_group(self, section=None):
        """Render shared or A/B talkback settings in documented node order."""
        config = self.state.talk_config
        if section is None:
            return "/config/talk %s %s\\n" % (
                ("OFF", "ON")[config["enable"]], ("INT", "EXT")[config["source"]])
        values = config[section]
        return "/config/talk/%s %.1f %s %s %s\\n" % (
            section, values["level"], ("OFF", "ON")[values["dim"]],
            ("OFF", "ON")[values["latch"]], "%" + format(values["destmap"], "018b"))

    def _config_osc_node_group(self):
        """Render the six oscillator generator settings in protocol order."""
        values = self.state.osc_config
        return "/config/osc %.1f %.3f %.3f %s %s %d\n" % (
            values["level"], values["f1"], values["f2"],
            ("F1", "F2")[values["fsel"]],
            ("SINE", "PINK", "WHITE")[values["type"]], values["dest"])

    def _config_mute_node_group(self):
        """Render all six mute-group selection states."""
        return "".join("/config/mute/%d %s\n" % (
            number, "ON" if enabled else "OFF")
            for number, enabled in self.state.mute_groups.items())

    def _config_routing_node_group(self, header="config/routing"):
        """Build a routing X32node response from the documented patch-bank entries."""
        from m32_monitor.routing import ROUTING_PATHS

        prefix = "/" + header
        if header == "config/routing":
            paths = [path for path in ROUTING_PATHS
                     if path.startswith("/config/routing/")
                     and path != "/config/routing/routswitch"]
        elif header in ("config/routing/outswitch", "config/routing/routswitch",
                        "config/routing/rootswitch"):
            paths = ["/" + header]
        else:
            paths = [path for path in ROUTING_PATHS
                     if path.startswith(prefix + "/")]
        return "".join("%s %s\n" % (path, self.state.routing.get(path)
                                      if self.state.routing.get(path) is not None else 0)
                       for path in paths)

    def _config_userctrl_node_group(self, bank, section=None):
        """Render a user-assignable control bank or its encoder/button sub-node."""
        values = self.state.user_controls[bank]
        color_names = ("OFF", "RD", "GN", "YE", "BL", "MG", "CY", "WH",
                       "OFFi", "RDi", "GNi", "YEi", "BLi", "MGi", "CYi", "WHi")
        if section == "enc":
            return "".join("/config/userctrl/%s/enc/%d %s\n" %
                           (bank, n, values["enc"][n]) for n in range(1, 5))
        if section == "btn":
            return "".join("/config/userctrl/%s/btn/%d %s\n" %
                           (bank, n, values["btn"][n]) for n in range(5, 13))
        lines = ["/config/userctrl/%s/color %s\n" % (bank, color_names[values["color"]])]
        lines.extend("/config/userctrl/%s/enc/%d %s\n" % (bank, n, values["enc"][n])
                     for n in range(1, 5))
        lines.extend("/config/userctrl/%s/btn/%d %s\n" % (bank, n, values["btn"][n])
                     for n in range(5, 13))
        return "".join(lines)

    def _config_tape_node_group(self):
        values = self.state.tape_config
        return ("/config/tape/gainL %.1f\n/config/tape/gainR %.1f\n"
                "/config/tape/autoplay %s\n" %
                (values["gainL"], values["gainR"], ("OFF", "ON")[values["autoplay"]]))

    def _config_amixenable_node_group(self):
        values = self.state.amix_enable
        return "".join("/config/amixenable/%s %s\n" % (group, ("OFF", "ON")[values[group]])
                       for group in ("X", "Y"))

    def _config_dp48_node_group(self, section=None):
        values = self.state.dp48_config
        if section == "link":
            return "".join("/config/dp48/link/%02d %d\n" % (n, values["link"][n])
                           for n in range(1, 25))
        if section == "assign":
            return "".join("/config/dp48/assign/%02d %d\n" % (n, values["assign"][n])
                           for n in range(1, 49))
        if section == "grpname":
            return "".join("/config/dp48/grpname/%02d %s\n" % (n, values["grpname"][n])
                           for n in range(1, 13))
        return ("/config/dp48/scope %s\n/config/dp48/broadcast %d\n"
                "/config/dp48/aesAB %s\n" %
                ("%" + format(int(values["scope"]), "04b"), values["broadcast"], ("AESA", "AESB")[values["aesAB"]]) +
                self._config_dp48_node_group("link") +
                self._config_dp48_node_group("assign") +
                self._config_dp48_node_group("grpname"))

    def _strip_node_header(self, header):
        parts = header.split("/")
        if len(parts) >= 3 and parts[:2] in (["main", "st"], ["main", "m"]):
            node = "/".join(parts[2:])
            schema = self.state.main_node_schema
            if node in schema:
                return "/" + "/".join(parts[:2]), node, tuple(schema[node])
            if len(parts) >= 4:
                parent, field = "/".join(parts[2:-1]), parts[-1]
                if parent in schema and field in schema[parent]:
                    return "/" + "/".join(parts[:2]), parent, (field,)
            return None
        if len(parts) < 3 or parts[0] not in self.state.strip_node_schema or not parts[1].isdigit():
            return None
        family = parts[0]
        number = int(parts[1])
        limit = {"ch": 32, "auxin": 8, "fxrtn": 8, "bus": 16, "mtx": 6}[family]
        if not 1 <= number <= limit:
            return None
        node = "/".join(parts[2:])
        schema = self.state.strip_node_schema[family]
        if node in schema:
            return "/" + family + "/" + parts[1], node, tuple(schema[node])
        if len(parts) >= 4:
            parent = "/".join(parts[2:-1])
            field = parts[-1]
            if parent in schema and field in schema[parent]:
                return "/" + family + "/" + parts[1], parent, (field,)
        return None

    @staticmethod
    def _parse_strip_node_value(spec, token):
        default, minimum, maximum, step, kind, labels = spec
        if kind == "string":
            return token
        if kind == "enum":
            return labels.index(token)
        if kind == "float":
            return float(token)
        return int(token, 0)

    @staticmethod
    def _format_strip_node_value(spec, value):
        default, minimum, maximum, step, kind, labels = spec
        if kind == "enum":
            return labels[int(value)]
        if kind == "string":
            return json.dumps(value, ensure_ascii=False)
        if kind == "float":
            return "%.3f" % float(value)
        return str(int(value))

    def _strip_node_response(self, prefix, node, fields):
        family = prefix.strip("/")
        schema = self.state.main_node_schema if family in ("main/st", "main/m") else self.state.strip_node_schema[family.split("/")[0]]
        specs = schema[node]
        values = []
        for field in fields:
            address = prefix + "/" + node + "/" + field
            value = self.state.get(address)
            if value is None:
                value = specs[field][0]
            values.append(self._format_strip_node_value(specs[field], value))
        return "%s %s\n" % (prefix + "/" + node, " ".join(values))

    def _handle_node(self, client, args):
        if len(args) != 1 or not isinstance(args[0], str):
            self.record("in", "unhandled_command", "/node", args, client,
                        "Expected exactly one X32node header string")
            return
        header = args[0].lstrip("/")
        if header == "config/routing" or header in (
                "config/routing/IN", "config/routing/AES50A",
                "config/routing/AES50B", "config/routing/CARD",
                "config/routing/OUT", "config/routing/PLAY",
                "config/routing/outswitch", "config/routing/routswitch",
                "config/routing/rootswitch"):
            response = self._config_routing_node_group(header)
            self.send(client, "/node", response, outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned %d routing configuration entries" %
                        len(response.splitlines()))
            return

        if header in ("config/userctrl/A", "config/userctrl/B", "config/userctrl/C"):
            bank = header[-1]
            self.send(client, "/node", self._config_userctrl_node_group(bank), outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned user control bank %s" % bank)
            return
        if header in ("config/userctrl/A/enc", "config/userctrl/B/enc", "config/userctrl/C/enc",
                      "config/userctrl/A/btn", "config/userctrl/B/btn", "config/userctrl/C/btn"):
            bank, section = header.split("/")[-2:]
            self.send(client, "/node", self._config_userctrl_node_group(bank, section), outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned user control %s %s assignments" % (bank, section))
            return
        if header == "config/tape":
            self.send(client, "/node", self._config_tape_node_group(), outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client, "Returned tape configuration")
            return
        if header == "config/amixenable":
            self.send(client, "/node", self._config_amixenable_node_group(), outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client, "Returned automix enable configuration")
            return
        if header == "config/dp48":
            self.send(client, "/node", self._config_dp48_node_group(), outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client, "Returned DP48 configuration")
            return
        if header in ("config/dp48/assign", "config/dp48/link", "config/dp48/grpname"):
            section = header.rsplit("/", 1)[1]
            self.send(client, "/node", self._config_dp48_node_group(section), outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned DP48 %s assignments" % section)
            return

        if header == "config/linkcfg":
            response = self._config_linkcfg_node_group()
            self.send(client, "/node", response, outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned linked-channel configuration flags")
            return

        if header == "config/mono":
            response = self._config_mono_node_group()
            self.send(client, "/node", response, outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned mono/centre output mode and Main L/R link settings")
            return

        if header == "config/solo":
            response = self._config_solo_node_group()
            self.send(client, "/node", response, outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned all 17 solo-monitor configuration fields")
            return

        if header in ("config/userrout/out", "config/userrout/in"):
            direction = header.rsplit("/", 1)[1]
            slots = self.state.user_rout_out if direction == "out" else self.state.user_rout_in
            response = "".join("/config/userrout/%s/%02d %d\n" % (direction, slot, source)
                               for slot, source in slots.items())
            self.send(client, "/node", response, outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned all %d user %s routing assignments" % (len(slots), direction))
            return

        if header.startswith(("config/userrout/out/", "config/userrout/in/")):
            address = "/" + header
            value = self.state.get(address)
            if value is None:
                self.record("in", "unhandled_command", "/node", args, client,
                            "No user routing slot is modelled for header %r" % header)
                return
            self.send(client, "/node", "%s %d\n" % (address, value), outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned individual user routing assignment")
            return

        if header.startswith("config/userctrl/") or header.startswith("config/tape/") or header.startswith("config/amixenable/") or header.startswith("config/dp48/"):
            address = "/" + header
            value = self.state.get(address)
            if value is None:
                self.record("in", "unhandled_command", "/node", args, client,
                            "No configuration value is modelled for header %r" % header)
                return
            if header.endswith("/color"):
                value = ("OFF", "RD", "GN", "YE", "BL", "MG", "CY", "WH",
                         "OFFi", "RDi", "GNi", "YEi", "BLi", "MGi", "CYi", "WHi")[int(value)]
            elif header.endswith("/autoplay"):
                value = ("OFF", "ON")[int(value)]
            elif header.endswith("/aesAB"):
                value = ("AESA", "AESB")[int(value)]
            elif header.startswith("config/amixenable/") or header.endswith("/autoplay"):
                value = ("OFF", "ON")[int(value)]
            elif header.endswith("/scope"):
                value = "%" + format(int(value), "04b")
            elif header.endswith("/broadcast") or "/link/" in header or "/assign/" in header:
                value = str(int(value))
            elif isinstance(value, float):
                value = "%.1f" % value
            self.send(client, "/node", "%s %s\n" % (address, value), outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned individual configuration value")
            return

        if header == "config/osc":
            self.send(client, "/node", self._config_osc_node_group(), outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned all six oscillator generator settings")
            return

        if header == "config/talk":
            self.send(client, "/node", self._config_talk_node_group(), outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned talkback enable and source configuration")
            return
        if header in ("config/talk/A", "config/talk/B"):
            section = header.rsplit("/", 1)[1]
            self.send(client, "/node", self._config_talk_node_group(section), outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned talkback %s configuration" % section)
            return

        if header == "config/mute":
            response = self._config_mute_node_group()
            self.send(client, "/node", response, outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned all six mute-group selection states")
            return

        if header in ("config/chlink", "config/auxlink", "config/fxlink",
                      "config/buslink", "config/mtxlink"):
            family = header.split("/", 1)[1]
            response = self._config_link_node_group(family)
            self.send(client, "/node", response, outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned %s stereo-link configuration (%d pairs)" % (
                            family, len(self.state.config_links[family])))
            return

        if header == "-urec":
            self.send(client, "/node", self._urec_node_group(), outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned X-Live recorder status node (16 fields)")
            return

        if header == "-prefs/rta":
            self.send(client, "/node", self._rta_node_group(), outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned all ten RTA preference fields")
            return
        if header.startswith("config/osc/"):
            address = "/" + header
            value = self.state.get(address)
            if value is None:
                self.record("in", "unhandled_command", "/node", args, client,
                            "No oscillator value is modelled for header %r" % header)
                return
            field = header.rsplit("/", 1)[1]
            if field == "fsel":
                rendered = ("F1", "F2")[int(value)]
            elif field == "type":
                rendered = ("SINE", "PINK", "WHITE")[int(value)]
            elif field == "level":
                rendered = "%.1f" % float(value)
            elif field in ("f1", "f2"):
                rendered = "%.3f" % float(value)
            else:
                rendered = str(int(value))
            self.send(client, "/node", "%s %s\\n" % (address, rendered), outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned individual oscillator configuration value")
            return
        if header.startswith("config/talk/"):
            address = "/" + header
            value = self.state.get(address)
            if value is None:
                self.record("in", "unhandled_command", "/node", args, client,
                            "No talkback value is modelled for header %r" % header)
                return
            field = header.rsplit("/", 1)[1]
            if field in ("enable", "dim", "latch"):
                rendered = ("OFF", "ON")[int(value)]
            elif field == "source":
                rendered = ("INT", "EXT")[int(value)]
            elif field == "destmap":
                rendered = "%" + format(int(value), "018b")
            else:
                rendered = "%.1f" % float(value)
            self.send(client, "/node", "%s %s\\n" % (address, rendered), outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned individual talkback configuration value")
            return
        if header.startswith("-urec/") or header.startswith("-stat/urec/"):
            address = "/" + header
            value = self.state.get(address)
            if value is None:
                self.record("in", "unhandled_command", "/node", args, client,
                            "No X-Live recorder value is modelled for header %r" % header)
                return
            enum_values = {
                "-urec/batterystate": ("NONE", "GOOD", "LOW"),
                "-urec/sd1state": ("NONE", "READY", "PROTECT", "ERROR"),
                "-urec/sd2state": ("NONE", "READY", "PROTECT", "ERROR"),
                "-stat/urec/state": ("STOP", "PPAUSE", "PLAY", "REC"),
            }
            if header in enum_values:
                rendered = enum_values[header][int(value)]
            elif isinstance(value, str):
                rendered = json.dumps(value, ensure_ascii=False)
            else:
                rendered = str(int(value))
            self.send(client, "/node", "%s %s\n" % (address, rendered),
                      outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned X-Live recorder value")
            return
        if header == "-prefs/card":
            names = tuple(self.state.card_preferences)
            values = " ".join(str(self.state.card_preferences[name]) for name in names)
            self.send(client, "/node", "/-prefs/card " + values + "\n", outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned card preference node (%d values)" % len(names))
            return
        if header in ("-prefs/rta/visibility", "-prefs/rta/gain", "-prefs/rta/autogain", "-prefs/rta/source", "-prefs/rta/pos", "-prefs/rta/mode", "-prefs/rta/options", "-prefs/rta/option", "-prefs/rta/det", "-prefs/rta/decay", "-prefs/rta/peakhold", "-stat/keysolo", "-stat/rtamodeeq", "-stat/rtamodegeq", "-stat/rtaeqpre", "-stat/rtageqpost", "-stat/rtasource"):
            address = "/" + header
            value = self.state.get(address)
            if value is None:
                value = 0
            if header.endswith(("/gain", "/decay")):
                response = "%s %.6f\n" % (address, float(value))
                detail = "Returned RTA floating-point preference X32node"
            else:
                response = "%s %s\n" % (address, self._rta_node_value(header, value))
                if header.endswith("/autogain"):
                    detail = "Returned RTA autogain X32node"
                elif header.endswith("/source"):
                    detail = "Returned RTA source X32node"
                elif header.endswith("/keysolo"):
                    detail = "Returned key solo status X32node"
                elif header.endswith("/pos"):
                    detail = "Returned RTA pre/post EQ position X32node"
                elif header.endswith("/mode"):
                    detail = "Returned RTA bar/spectrograph mode X32node"
                elif header.endswith(("/options", "/option")):
                    detail = "Returned RTA options bitmask X32node"
                elif header.endswith("/det"):
                    detail = "Returned RTA detector selection X32node"
                elif header.endswith("/peakhold"):
                    detail = "Returned RTA peak-hold selection X32node"
                elif header.endswith("/rtamodeeq"):
                    detail = "Returned RTA EQ display mode status X32node"
                elif header.endswith("/rtamodegeq"):
                    detail = "Returned RTA GEQ display mode status X32node"
                elif header.endswith("/rtaeqpre"):
                    detail = "Returned RTA pre-EQ status X32node"
                elif header.endswith("/rtageqpost"):
                    detail = "Returned RTA post-GEQ status X32node"
                elif header.endswith("/rtasource"):
                    detail = "Returned active RTA source status X32node"
                else:
                    detail = "Returned RTA visibility X32node"
            self.send(client, "/node", response, outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client, detail)
            return
        # M32-Edit explicitly requests each strip's config parent node. Keep
        # this route explicit rather than relying on the generic processing-node
        # resolver: it is part of the initial channel discovery handshake.
        config_parts = header.split("/")
        if header in ("main/st/config", "main/m/config"):
            prefix = "/" + header.rsplit("/", 1)[0]
            response = self._strip_node_response(prefix, "config", tuple(self.state.main_node_schema["config"]))
            self.send(client, "/node", response, outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned %s config discovery node" % header)
            return
        if (len(config_parts) == 3 and config_parts[0] in self.state.strip_node_schema
                and config_parts[1].isdigit() and config_parts[2] == "config"):
            family, number = config_parts[0], int(config_parts[1])
            limit = {"ch": 32, "auxin": 8, "fxrtn": 8, "bus": 16, "mtx": 6}[family]
            if 1 <= number <= limit:
                prefix = "/" + family + "/" + config_parts[1]
                fields = tuple(self.state.strip_node_schema[family]["config"])
                response = self._strip_node_response(prefix, "config", fields)
                self.send(client, "/node", response, outcome="node_response")
                self.record("in", "handled_node_get", "/node", args, client,
                            "Returned %s %02d config discovery node" % (family, number))
                return

        output_parts = header.split("/")
        if (len(output_parts) in (3, 4) and output_parts[0] == "outputs"
                and output_parts[1] in ("main", "aux", "p16", "aes", "rec") and output_parts[2].isdigit()):
            family = output_parts[1]
            collection = {"main": self.state.output_main, "aux": self.state.output_aux, "p16": self.state.output_p16, "aes": self.state.output_aes, "rec": self.state.output_rec}[family]
            number = int(output_parts[2])
            if number in collection:
                prefix = "/outputs/%s/%02d" % (family, number)
                output = collection[number]
                positions = ("IN/LC", "IN/LC+M", "<-EQ", "<-EQ+M", "EQ->", "EQ->+M", "PRE", "PRE+M", "POST")
                speakers = ("none", "iQ8", "iQ10", "iQ12", "iQ15", "iQ15B", "iQ18B")
                if len(output_parts) == 3 and family in ("p16", "rec"):
                    response = "%s/src %d\n%s/pos %s\n" % (prefix, output["src"], prefix, positions[output["pos"]])
                elif len(output_parts) == 3:
                    response = ("%s/src %d\n%s/pos %s\n%s/invert %s\n" % (
                        prefix, output["src"], prefix, positions[output["pos"]], prefix,
                        ("OFF", "ON")[output["invert"]]))
                elif output_parts[3] == "iQ" and family == "p16":
                    response = "%s/iQ/group %s\n%s/iQ/speaker %s\n" % (
                        prefix, ("OFF", "A", "B")[output["iq_group"]], prefix, speakers[output["iq_speaker"]])
                elif output_parts[3] == "delay" and family == "main":
                    response = "%s/delay/on %s\n%s/delay/time %.1f\n" % (
                        prefix, ("OFF", "ON")[output["delay_on"]], prefix, output["delay_time"])
                elif output_parts[3] == "src": response = "%s/src %d\n" % (prefix, output["src"])
                elif output_parts[3] == "pos": response = "%s/pos %s\n" % (prefix, positions[output["pos"]])
                elif output_parts[3] == "invert" and family in ("main", "aux", "aes"): response = "%s/invert %s\n" % (prefix, ("OFF", "ON")[output["invert"]])
                else: response = None
                if response is not None:
                    self.send(client, "/node", response, outcome="node_response")
                    self.record("in", "handled_node_get", "/node", args, client,
                                "Returned physical %s output %02d %s node" % (family, number, output_parts[3] if len(output_parts) == 4 else "configuration"))
                    return
        if len(output_parts) == 5 and output_parts[0] == "outputs" and output_parts[1] == "main" and output_parts[2].isdigit():
            number = int(output_parts[2])
            if number in self.state.output_main and output_parts[3:] in (["delay", "on"], ["delay", "time"]):
                value = self.state.get("/" + header)
                rendered = ("OFF", "ON")[int(value)] if output_parts[-1] == "on" else "%.1f" % value
                self.send(client, "/node", "/%s %s\n" % (header, rendered), outcome="node_response")
                self.record("in", "handled_node_get", "/node", args, client, "Returned physical output delay field")
                return
        if (len(output_parts) == 5 and output_parts[:2] == ["outputs", "p16"]
                and output_parts[2].isdigit() and int(output_parts[2]) in self.state.output_p16
                and output_parts[3] == "iQ" and output_parts[4] in ("group", "speaker")):
            number = int(output_parts[2])
            output = self.state.output_p16[number]
            if output_parts[4] == "group":
                value = ("OFF", "A", "B")[output["iq_group"]]
            else:
                value = ("none", "iQ8", "iQ10", "iQ12", "iQ15", "iQ15B", "iQ18B")[output["iq_speaker"]]
            self.send(client, "/node", "/%s %s\n" % (header, value), outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client, "Returned P16 iQ setting")
            return
        fx_parts = header.split("/")
        if (len(fx_parts) in (2, 3) and fx_parts[0] == "fx"
                and fx_parts[1].isdigit() and int(fx_parts[1]) in self.state.fx):
            number = int(fx_parts[1])
            prefix = "/fx/%02d" % number
            fx = self.state.fx[number]
            type_names = TYPE_NAMES_FX_1_4 if number <= 4 else TYPE_NAMES_FX_5_8
            source_names = ("INS",) + tuple("MIX%d" % n for n in range(1, 17)) + ("M/C",)
            if len(fx_parts) == 2 or fx_parts[2] == "type":
                response = "%s/type %s\n" % (prefix, type_names[fx["type"]])
            elif fx_parts[2] == "source" and number <= 4:
                response = "%s/source %s %s\n" % (
                    prefix, source_names[fx["source_l"]], source_names[fx["source_r"]])
            elif fx_parts[2] == "par":
                response = "".join("%s/par/%02d %.6f\n" % (prefix, n, fx["par"][n])
                                   for n in range(1, 65))
            else:
                response = None
            if response is not None:
                self.send(client, "/node", response, outcome="node_response")
                self.record("in", "handled_node_get", "/node", args, client,
                            "Returned FX slot %d %s node" % (number, fx_parts[2] if len(fx_parts) == 3 else "type"))
                return
        if len(fx_parts) == 4 and fx_parts[0] == "fx" and fx_parts[1].isdigit():
            number = int(fx_parts[1])
            if number in self.state.fx and fx_parts[2] == "par" and fx_parts[3].isdigit():
                parameter = int(fx_parts[3])
                if 1 <= parameter <= 64:
                    value = self.state.fx[number]["par"][parameter]
                    self.send(client, "/node", "%s %.6f\n" % ("/" + header, value), outcome="node_response")
                    self.record("in", "handled_node_get", "/node", args, client, "Returned FX parameter")
                    return
            if number in self.state.fx and fx_parts[2] == "source" and fx_parts[3] in ("l", "r") and number <= 4:
                value = self.state.fx[number]["source_" + fx_parts[3]]
                source_names = ("INS",) + tuple("MIX%d" % n for n in range(1, 17)) + ("M/C",)
                self.send(client, "/node", "%s %s\n" % ("/" + header, source_names[value]), outcome="node_response")
                self.record("in", "handled_node_get", "/node", args, client, "Returned FX source field")
                return
        dca_parts = header.split("/")
        if (len(dca_parts) in (2, 3) and dca_parts[0] == "dca"
                and dca_parts[1].isdigit() and int(dca_parts[1]) in self.state.dcas):
            number = int(dca_parts[1])
            prefix = "/dca/%d" % number
            dca = self.state.dcas[number]
            colour_names = ("OFF", "RD", "GN", "YE", "BL", "MG", "CY", "WH",
                            "OFFi", "RDi", "GNi", "YEi", "BLi", "MGi", "CYi", "WHi")
            if len(dca_parts) == 2:
                response = ("%s/on %s\n%s/fader %.3f\n%s/config/name %s\n"
                            "%s/config/icon %d\n%s/config/color %s\n" % (
                                prefix, "ON" if dca["on"] else "OFF", prefix, dca["fader"],
                                prefix, json.dumps(dca["name"], ensure_ascii=False), prefix,
                                dca["icon"], prefix, colour_names[dca["colour"]]))
            else:
                response = "%s/config %s %d %s\n" % (
                    prefix, json.dumps(dca["name"], ensure_ascii=False), dca["icon"],
                    colour_names[dca["colour"]])
            self.send(client, "/node", response, outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned DCA %d %s node" % (number, "complete" if len(dca_parts) == 2 else "config"))
            return
        strip_node = self._strip_node_header(header)
        if strip_node is not None:
            prefix, node, fields = strip_node
            if header != prefix.lstrip("/") + "/" + node:
                field = fields[0]
                schema = self.state.main_node_schema if prefix in ("/main/st", "/main/m") else self.state.strip_node_schema[header.split("/")[0]]
                spec = schema[node][field]
                value = self.state.get(prefix + "/" + node + "/" + field)
                response = "%s %s\n" % ("/" + header, self._format_strip_node_value(spec, value))
            else:
                response = self._strip_node_response(prefix, node, fields)
            self.send(client, "/node", response, outcome="node_response")
            self.record("in", "handled_node_get", "/node", args, client,
                        "Returned %s processing node (%d values)" % (node, len(fields)))
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
                        name.lstrip("/") == key[1].lstrip("/"))]
            format_matching = [key for key in self.format_subscriptions
                               if key[0] == client and (name is None or
                               name in (key[1], key[1].lstrip("/")))]
            if address == "/renew":
                for key in matching:
                    self.batch_subscriptions[key]["expires_at"] = time.monotonic() + 10.0
                for key in format_matching:
                    self.format_subscriptions[key]["expires_at"] = time.monotonic() + 10.0
            else:
                if not args:
                    self.clients.discard(client)
                    matching = [key for key in self.batch_subscriptions if key[0] == client]
                for key in matching:
                    self.batch_subscriptions.pop(key, None)
                    task = self.subscription_tasks.pop(key, None)
                    if task:
                        task.cancel()
                for key in format_matching:
                    self.format_subscriptions.pop(key, None)
                    task = self.format_tasks.pop(key, None)
                    if task:
                        task.cancel()
            outcome = "handled_renewal" if address == "/renew" else "handled_unsubscription"
            self.record("in", outcome, address, args, client,
                        "Subscription maintenance request accepted (%d meter and %d formatted subscription(s) matched)" % (len(matching), len(format_matching)))
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
        if address == "/formatsubscribe":
            self._handle_formatsubscribe(client, args)
            return
        if address == "/node":
            self._handle_node(client, args)
            return
        if address == "/":
            self._handle_node_set(client, args)
            return
        if address == "/showdump":
            show_response = '/-showfile/show "" 0 0 0 0 0 0 0 0 0 "4.06"'
            self.send(client, "/node", show_response, outcome="showdump_response")
            self.record("in", "handled_showdump", address, args, client,
                        "Returned empty show metadata (no stored show data is modelled)")
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
