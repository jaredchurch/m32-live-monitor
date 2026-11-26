"""Read-only OSC client for a physical M32."""
import asyncio
import logging
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient

logger = logging.getLogger(__name__)

class HardwareMonitor:
    """Listen for M32 updates and issue parameter enquiries; never sends SETs."""
    def __init__(self,state,host,port,listen_host,listen_port):
        self.state,self.host,self.port=state,host,port
        self.listen_host,self.listen_port=listen_host,listen_port
        self.transport=None
        self.client=SimpleUDPClient(host,port)
        self.keepalive=None

    async def start(self):
        dispatcher=Dispatcher()
        dispatcher.set_default_handler(self._handle)
        server=AsyncIOOSCUDPServer((self.listen_host,self.listen_port),dispatcher,asyncio.get_running_loop())
        self.transport,_=await server.create_serve_endpoint()
        self.state.mode="hardware"; self.state.online=False
        self.keepalive=asyncio.create_task(self._refresh())
        logger.info("Read-only M32 monitor started for %s:%s",self.host,self.port)

    async def stop(self):
        if self.keepalive:
            self.keepalive.cancel(); self.keepalive=None
        if self.transport:
            self.transport.close(); self.transport=None

    async def _refresh(self):
        while True:
            try:
                self.client.send_message("/xremote",[])
                self.client.send_message("/info",[])
                for number in range(1,33):
                    prefix="/ch/%02d" % number
                    for suffix in ("config/name","config/color","config/source","mix/fader","mix/on"):
                        self.client.send_message(prefix+"/"+suffix,[])
                        await asyncio.sleep(0.012)
            except OSError:
                logger.exception("M32 OSC enquiry failed")
            await asyncio.sleep(8)

    def _handle(self,address,*args):
        if address=="/info": self.state.online=True; return
        if args and self.state.update(address,args[0]): self.state.online=True
