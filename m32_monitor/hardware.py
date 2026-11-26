"""Read-only OSC client for a physical M32 console."""
import asyncio
import logging
import socket

from pythonosc.osc_packet import OscPacket, ParseError
from pythonosc.osc_message_builder import OscMessageBuilder

logger = logging.getLogger(__name__)


class HardwareMonitor:
    """Listen for M32 updates and issue parameter enquiries; never sends SETs."""

    def __init__(self, state, host, port, listen_host, listen_port):
        self.state, self.host, self.port = state, host, port
        self.listen_host, self.listen_port = listen_host, listen_port
        self.sock = None
        self.receiver = self.keepalive = self.query_task = None

    async def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.sock.bind((self.listen_host, self.listen_port))
        self.state.mode = "hardware"
        self.state.received.clear()
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

    async def _keepalive(self):
        while True:
            try:
                self._send("/xremote")
            except OSError:
                logger.exception("M32 OSC keepalive failed")
            await asyncio.sleep(5)

    async def _query_console(self):
        """Refresh the routing/mute snapshot in small UDP bursts."""
        while True:
            try:
                addresses = ["/info"]
                for family, count in (("ch", 32), ("auxin", 8), ("fxrtn", 8)):
                    for number in range(1, count + 1):
                        prefix = "/%s/%02d" % (family, number)
                        suffixes = ["config/name", "config/color", "mix/fader", "mix/on",
                                    "mix/st", "mix/mono", "grp/dca", "grp/mute"]
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
                    addresses.extend((prefix + "/mix/on", prefix + "/mix/fader",
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
                for address in addresses:
                    self._send(address)
                    await asyncio.sleep(0.01)
            except OSError:
                logger.exception("M32 OSC enquiry failed")
            await asyncio.sleep(30)

    def _process_datagram(self, data):
        """Apply OSC messages from either a single message or an OSC bundle."""
        try:
            packet = OscPacket(data)
            for timed_message in packet.messages:
                message = timed_message.message
                if message.address == "/info":
                    self.state.mark_seen()
                elif message.params and self.state.update(
                    message.address, message.params[0]
                ):
                    self.state.mark_seen()
        except (ValueError, IndexError, ParseError):
            logger.debug("Ignoring unrecognised OSC datagram", exc_info=True)

    async def _receive(self):
        loop = asyncio.get_running_loop()
        while True:
            data, _peer = await loop.sock_recvfrom(self.sock, 65535)
            self._process_datagram(data)
