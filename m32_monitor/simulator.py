"""OSC simulator for the subset currently used by this app."""
import logging
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient

logger = logging.getLogger(__name__)

class Simulator:
    def __init__(self, state, host="0.0.0.0", port=10023):
        self.state, self.host, self.port = state, host, port
        self.transport = None
        self.clients = set()

    async def start(self):
        dispatcher = Dispatcher()
        dispatcher.set_default_handler(self._handle, needs_reply_address=True)
        server = AsyncIOOSCUDPServer((self.host,self.port), dispatcher, __import__("asyncio").get_running_loop())
        self.transport, _ = await server.create_serve_endpoint()
        logger.info("Simulator listening on UDP %s", self.port)

    async def stop(self):
        if self.transport:
            self.transport.close()
            self.transport = None

    def _send(self, client, address, value):
        SimpleUDPClient(client[0],client[1]).send_message(address,value)

    def _handle(self, client, address, *args):
        if address in ("/xremote","/subscribe"):
            self.clients.add(client); return
        if address == "/info":
            self._send(client,"/info",["1.0","M32-Live-Monitor-Simulator","M32","1.0"]); return
        if address == "/status":
            self._send(client,"/status","active"); return
        if args:
            if self.state.update(address,args[0]):
                for subscriber in tuple(self.clients):
                    self._send(subscriber,address,args[0])
            return
        value = self.state.get(address)
        if value is not None: self._send(client,address,value)
