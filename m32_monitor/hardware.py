"""Read-only OSC client for a physical M32.

A single UDP socket is used for both sending and receiving so the console's
replies return to the port on which this client is listening.
"""
import asyncio
import logging
import socket
from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import OscMessageBuilder

logger = logging.getLogger(__name__)

class HardwareMonitor:
    """Listen for M32 updates and issue parameter enquiries; never sends SETs."""
    def __init__(self,state,host,port,listen_host,listen_port):
        self.state,self.host,self.port=state,host,port
        self.listen_host,self.listen_port=listen_host,listen_port
        self.sock=None
        self.receiver=None
        self.keepalive=None

    async def start(self):
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.sock.bind((self.listen_host,self.listen_port))
        self.state.mode="hardware"
        self.state.online=False
        self.receiver=asyncio.create_task(self._receive())
        self.keepalive=asyncio.create_task(self._refresh())
        logger.info("Read-only M32 monitor started for %s:%s",self.host,self.port)

    async def stop(self):
        for task in (self.keepalive,self.receiver):
            if task: task.cancel()
        self.keepalive=self.receiver=None
        if self.sock:
            self.sock.close()
            self.sock=None

    def _send(self,address):
        builder=OscMessageBuilder(address=address)
        self.sock.sendto(builder.build().dgram,(self.host,self.port))

    async def _refresh(self):
        while True:
            try:
                self._send("/xremote")
                self._send("/info")
                for number in range(1,33):
                    prefix="/ch/%02d" % number
                    for suffix in ("config/name","config/color","config/source","mix/fader","mix/on"):
                        self._send(prefix+"/"+suffix)
                        await asyncio.sleep(0.012)
            except OSError:
                logger.exception("M32 OSC enquiry failed")
            await asyncio.sleep(8)

    async def _receive(self):
        loop=asyncio.get_running_loop()
        while True:
            data,_peer=await loop.sock_recvfrom(self.sock,65535)
            try:
                message=OscMessage(data)
                if message.address=="/info":
                    self.state.online=True
                elif message.params and self.state.update(message.address,message.params[0]):
                    self.state.online=True
            except (ValueError, IndexError):
                logger.debug("Ignoring unrecognised OSC datagram",exc_info=True)
