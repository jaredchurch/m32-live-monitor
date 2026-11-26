"""Read-only OSC client for a physical M32 console."""
import asyncio
import logging
import socket
import time

from pythonosc.osc_packet import OscPacket, ParseError
from pythonosc.osc_message_builder import OscMessageBuilder
from m32_monitor.diagnostics import OscDiagnostics

logger = logging.getLogger(__name__)


class HardwareMonitor:
    """Listen for M32 updates and issue parameter enquiries; never sends SETs."""

    def __init__(self, state, host, port, listen_host, listen_port):
        self.state, self.host, self.port = state, host, port
        self.listen_host, self.listen_port = listen_host, listen_port
        self.sock = None
        self.diagnostics = OscDiagnostics(host)
        self.receiver = self.keepalive = self.query_task = None

    async def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.sock.bind((self.listen_host, self.listen_port))
        self.state.mode = "hardware"
        self.state.received.clear()
        self.state.routing.values.clear()
        self.state.meters.clear()
        self.state.last_seen = None
        for collection in (self.state.channels, self.state.auxins, self.state.fx_returns):
            for channel in collection.values():
                channel.source = 0
                channel.connected = False
                channel.colour = 0
        self.receiver = asyncio.create_task(self._receive())
        self.keepalive = asyncio.create_task(self._keepalive())
        self.query_task = asyncio.create_task(self._query_console())
        logger.info("Read-only M32 monitor started for %s:%s", self.host, self.port)

    async def stop(self):
        for task in (self.keepalive, self.query_task, self.receiver):
            if task:
                task.cancel()
        self.keepalive = self.query_task = self.receiver = None
        if self.sock:
            self.sock.close()
            self.sock = None

    def _send(self, address):
        """Send an OSC enquiry/subscription message; no parameter SETs are issued."""
        builder = OscMessageBuilder(address=address)
        self.sock.sendto(builder.build().dgram, (self.host, self.port))

    def _send_meter_subscription(self, meter_id, interval=4):
        """Subscribe to one documented M32 meter stream (200 ms update interval)."""
        builder = OscMessageBuilder(address="/meters")
        builder.add_arg("/meters/%d" % meter_id)
        builder.add_arg(interval)
        self.sock.sendto(builder.build().dgram, (self.host, self.port))

    async def _keepalive(self):
        while True:
            try:
                self._send("/xremote")
                for meter_id in (0, 2, 4, 9, 11):
                    self._send_meter_subscription(meter_id)
            except OSError as exc:
                self.diagnostics.event("send_errors", exc, detail="keepalive / meter subscription")
                logger.exception("M32 OSC keepalive failed")
            await asyncio.sleep(5)

    async def _query_console(self):
        """Refresh the routing/mute snapshot in small UDP bursts."""
        while True:
            try:
                addresses = ["/info"]
                # Patchbay snapshots: block selections are enum values in the M32 OSC protocol.
                for path in (
                    "/config/routing/IN/1-8", "/config/routing/IN/9-16",
                    "/config/routing/IN/17-24", "/config/routing/IN/25-32",
                    "/config/routing/IN/AUX", "/config/routing/outswitch",
                    "/config/routing/routswitch",
                ):
                    addresses.append(path)
                for family in ("AES50A", "AES50B"):
                    for bank in ("1-8", "9-16", "17-24", "25-32", "33-40", "41-48"):
                        addresses.append("/config/routing/%s/%s" % (family, bank))
                for bank in ("1-8", "9-16", "17-24", "25-32"):
                    addresses.append("/config/routing/CARD/%s" % bank)
                    addresses.append("/config/routing/PLAY/%s" % bank)
                addresses.extend("/config/routing/OUT/%s" % bank for bank in ("1-4", "5-8", "9-12", "13-16"))
                addresses.extend(("/config/routing/PLAY/AUX",))
                for family, count in (("main", 16), ("aux", 6), ("p16", 16), ("aes", 2)):
                    for number in range(1, count + 1):
                        prefix = "/outputs/%s/%02d" % (family, number)
                        addresses.extend((prefix + "/src", prefix + "/pos", prefix + "/invert"))
                        if family == "main":
                            addresses.extend((prefix + "/delay/on", prefix + "/delay/time"))
                        if family == "p16":
                            addresses.extend((prefix + "/iQ/group", prefix + "/iQ/speaker", prefix + "/iQ/eq"))
                for number in range(1, 9):
                    addresses.extend(("/fx/%d/type" % number, "/fx/%d/source" % number, "/fx/%d/par" % number))
                addresses.extend(("/config/solo/level", "/config/solo/source", "/config/solo/sourcetrim",
                                  "/config/solo/chmode", "/config/solo/busmode", "/config/solo/dcamode",
                                  "/config/solo/exclusive", "/config/solo/followsel", "/config/solo/followsolo",
                                  "/config/solo/dimatt", "/config/solo/dim", "/config/solo/mono",
                                  "/config/solo/delay", "/config/solo/delaytime", "/config/solo/masterctrl",
                                  "/config/solo/mute", "/config/solo/dimpfl",
                                  "/config/talk/enable", "/config/talk/source",
                                  "/config/talk/A/level", "/config/talk/B/level",
                                  "/config/talk/A/dim", "/config/talk/B/dim",
                                  "/config/talk/A/latch", "/config/talk/B/latch",
                                  "/config/talk/A/latch", "/config/talk/B/latch",
                                  "/config/talk/A/destmap", "/config/talk/B/destmap"))
                addresses.extend("/config/userrout/out/%02d" % number for number in range(1, 49))
                addresses.extend("/config/userrout/in/%02d" % number for number in range(1, 33))
                # Stereo links and pan/balance affect the interpretation of the signal path.
                for family, count in (("ch", 32), ("auxin", 8), ("fxrtn", 8), ("bus", 16), ("mtx", 6)):
                    for number in range(1, count + 1):
                        addresses.append("/%s/%02d/mix/pan" % (family, number))
                addresses.extend(("/main/st/mix/pan", "/main/m/mix/pan"))
                for path in ("chlink", "auxlink", "fxlink", "buslink", "mtxlink"):
                    maximum = 32 if path == "chlink" else 8 if path in ("auxlink", "fxlink") else 16 if path == "buslink" else 6
                    for number in range(1, maximum, 2):
                        addresses.append("/config/%s/%d-%d" % (path, number, number + 1))
                addresses.extend(("/config/mono/mode", "/config/mono/link"))
                for family, count in (("ch", 32), ("auxin", 8), ("fxrtn", 8), ("bus", 16), ("mtx", 6)):
                    for number in range(1, count + 1):
                        addresses.append("/%s/%02d/insert" % (family, number))
                addresses.extend(("/main/st/insert", "/main/m/insert"))
                for family, count in (("ch", 32), ("auxin", 8), ("fxrtn", 8)):
                    for number in range(1, count + 1):
                        prefix = "/%s/%02d" % (family, number)
                        suffixes = ["config/name", "config/color", "mix/fader", "mix/on",
                                    "mix/st", "mix/mono", "mix/mlevel", "grp/dca", "grp/mute"]
                        if family != "fxrtn":
                            suffixes.append("config/source")
                        addresses.extend(prefix + "/" + suffix for suffix in suffixes)
                        for bus in range(1, 17):
                            if bus % 2:
                                addresses.append(prefix + "/mix/%02d/type" % bus)
                            addresses.extend((prefix + "/mix/%02d/on" % bus,
                                              prefix + "/mix/%02d/level" % bus))
                for number in range(1, 9):
                    addresses.extend(("/dca/%d/on" % number, "/dca/%d/fader" % number))
                addresses.extend("/config/mute/%d" % number for number in range(1, 7))
                addresses.extend(("/-prefs/dcamute", "/-prefs/hardmute"))
                for number in range(1, 17):
                    prefix = "/bus/%02d" % number
                    addresses.extend((prefix + "/config/name", prefix + "/mix/on", prefix + "/mix/fader",
                                      prefix + "/grp/dca", prefix + "/grp/mute"))
                    for matrix in range(1, 7):
                        addresses.extend((prefix + "/mix/%02d/on" % matrix,
                                          prefix + "/mix/%02d/level" % matrix))
                for prefix in ("/main/st", "/main/m"):
                    addresses.extend((prefix + "/mix/on", prefix + "/mix/fader",
                                      prefix + "/grp/dca", prefix + "/grp/mute"))
                    for matrix in range(1, 7):
                        addresses.extend((prefix + "/mix/%02d/on" % matrix,
                                          prefix + "/mix/%02d/level" % matrix))
                for number in range(1, 7):
                    prefix = "/mtx/%02d" % number
                    addresses.extend((prefix + "/config/name", prefix + "/mix/on",
                                      prefix + "/mix/fader", prefix + "/grp/dca",
                                      prefix + "/grp/mute"))
                self.diagnostics.begin_cycle(addresses)
                for address in addresses:
                    self._send(address)
                    await asyncio.sleep(0.01)
            except OSError as exc:
                self.diagnostics.event("send_errors", exc, detail="parameter enquiry cycle")
                logger.exception("M32 OSC enquiry failed")
            self.diagnostics.last_cycle_at = time.time()
            await asyncio.sleep(30)

    @staticmethod
    def _response_format_error(address, params):
        """Return a reason when OSC argument shape/type is implausible."""
        if address == "/info":
            return None
        if address.startswith("/meters/"):
            return None if len(params) == 1 and isinstance(params[0], (bytes, bytearray)) else "meter response must contain one binary blob"
        if not params:
            return "expected at least one OSC argument"
        if address.endswith("/config/name"):
            return None if len(params) == 1 and isinstance(params[0], str) else "name response must contain one string"
        if (address.startswith("/fx/") and address.endswith("/par")) or "/insert" in address:
            valid = all(isinstance(value, (int, float, bool)) for value in params)
            return None if valid else "FX/insert parameters must be numeric"
        valid = len(params) == 1 and isinstance(params[0], (int, float, bool))
        return None if valid else "expected one numeric OSC argument"
    def _process_datagram(self, data, peer=None):
        """Apply OSC messages and retain actionable protocol diagnostics."""
        if peer:
            try:
                expected_ip = socket.gethostbyname(self.host)
                if peer[0] != expected_ip:
                    self.diagnostics.event("unexpected_peers", "OSC packet received from unexpected host", detail={"peer": peer[0], "expected": expected_ip})
                    return
            except OSError as exc:
                self.diagnostics.event("dns_errors", exc, detail=self.host)
        try:
            packet = OscPacket(data)
            for timed_message in packet.messages:
                message = timed_message.message
                if message.address == "/info":
                    self.diagnostics.received(message.address)
                    self.state.mark_seen()
                elif message.address.startswith("/meters/"):
                    if len(message.params) == 1 and self.state.update_meter(message.address, message.params[0]):
                        self.diagnostics.received(message.address)
                        self.state.mark_seen()
                    else:
                        self.diagnostics.event("invalid_responses", "Malformed or unsupported meter response", message.address,
                                               {"argument_count": len(message.params), "argument_types": [type(x).__name__ for x in message.params]})
                elif message.params:
                    format_error = self._response_format_error(message.address, message.params)
                    if format_error:
                        self.diagnostics.event("invalid_responses", format_error, message.address,
                                               {"values": repr(message.params), "types": [type(x).__name__ for x in message.params]})
                        continue
                    value = message.params if message.address.startswith("/fx/") or "/insert" in message.address else message.params[0]
                    if self.state.update(message.address, value):
                        self.diagnostics.received(message.address)
                        self.state.mark_seen()
                    elif message.address in self.diagnostics.expected:
                        self.diagnostics.event("invalid_responses", "Expected OSC address returned an unsupported value or format",
                                               message.address, {"values": repr(message.params), "types": [type(x).__name__ for x in message.params]})
                    else:
                        self.diagnostics.event("unexpected_addresses", "Unrecognised OSC address", message.address,
                                               {"values": repr(message.params), "types": [type(x).__name__ for x in message.params]})
                else:
                    self.diagnostics.event("invalid_responses", "OSC response contained no arguments", message.address)
        except (ValueError, IndexError, ParseError) as exc:
            self.diagnostics.event("malformed_packets", exc, detail="OSC packet parse failed")
            logger.debug("Ignoring malformed OSC datagram", exc_info=True)

    async def _receive(self):
        loop = asyncio.get_running_loop()
        while True:
            try:
                data, peer = await loop.sock_recvfrom(self.sock, 65535)
                self._process_datagram(data, peer)
            except OSError as exc:
                self.diagnostics.event("receive_errors", exc, detail="OSC UDP receive")
                logger.exception("M32 OSC receive failed")
                await asyncio.sleep(1)
