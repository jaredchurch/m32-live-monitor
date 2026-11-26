"""UDP OSC simulator for the M32 parameter subset used by this app."""
import asyncio
import logging
from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import OscMessageBuilder

logger=logging.getLogger(__name__)

class Simulator:
    def __init__(self,state,host="0.0.0.0",port=10023):
        self.state,self.host,self.port=state,host,port
        self.transport=None
        self.clients=set()

    async def start(self):
        loop=asyncio.get_running_loop()
        self.transport,_=await loop.create_datagram_endpoint(lambda: SimulatorProtocol(self),
            local_addr=(self.host,self.port))
        logger.info("M32 simulator listening on UDP %s",self.port)

    async def stop(self):
        if self.transport:
            self.transport.close()
            self.transport=None

    def send(self,client,address,*values):
        builder=OscMessageBuilder(address=address)
        for value in values: builder.add_arg(value)
        self.transport.sendto(builder.build().dgram,client)

    def handle(self,client,data):
        try:
            message=OscMessage(data)
            address=message.address
            args=message.params
        except (ValueError,IndexError):
            logger.debug("Ignoring malformed OSC packet")
            return
        if address in ("/xremote","/subscribe"):
            self.clients.add(client)
            return
        if address=="/info":
            self.send(client,"/info","1.0","M32-Live-Monitor-Simulator","M32","1.0")
            return
        if address=="/xinfo":
            self.send(client,"/xinfo","M32-Live-Monitor-Simulator")
            return
        if address=="/status":
            self.send(client,"/status","active")
            return
        if args:
            if self.state.update(address,args[0]):
                for subscriber in tuple(self.clients):
                    self.send(subscriber,address,args[0])
            return
        value=self.state.get(address)
        if value is not None: self.send(client,address,value)

class SimulatorProtocol(asyncio.DatagramProtocol):
    def __init__(self,simulator):
        self.simulator=simulator
    def connection_made(self,transport):
        self.simulator.transport=transport
    def datagram_received(self,data,addr):
        self.simulator.handle(addr,data)
