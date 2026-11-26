import pytest
from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import OscMessageBuilder

from m32_monitor.simulator import Simulator
from m32_monitor.state import ConsoleState


class FakeTransport:
    def __init__(self):
        self.sent = []
    def sendto(self, data, address):
        self.sent.append((data, address))


def packet(address, *args):
    builder = OscMessageBuilder(address=address)
    for arg in args:
        builder.add_arg(arg)
    return builder.build().dgram


def test_simulator_answers_parameter_get():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/ch/01/mix/fader"))

    data, destination = simulator.transport.sent[0]
    response = OscMessage(data)
    assert destination == client
    assert response.address == "/ch/01/mix/fader"
    assert response.params[0] == pytest.approx(0.72)


def test_simulator_accepts_parameter_set_and_notifies_subscriber():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/xremote"))
    simulator.handle(client, packet("/ch/01/config/name", "W1 - Male"))

    assert state.channels[1].name == "W1 - Male"
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/ch/01/config/name"
    assert response.params == ["W1 - Male"]


def test_simulator_info_response_has_basic_identity():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/info"))
    response = OscMessage(simulator.transport.sent[0][0])
    assert response.address == "/info"
    assert response.params[2] == "M32"


def test_simulator_udp_round_trip():
    import asyncio
    import socket

    async def exercise():
        state = ConsoleState()
        simulator = Simulator(state, host="127.0.0.1", port=0)
        await simulator.start()
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.setblocking(False)
        loop = asyncio.get_running_loop()
        address = simulator.transport.get_extra_info("sockname")
        try:
            await loop.sock_sendto(client, packet("/ch/01/mix/fader"), address)
            data, _peer = await asyncio.wait_for(
                loop.sock_recvfrom(client, 4096), timeout=1
            )
            response = OscMessage(data)
            assert response.address == "/ch/01/mix/fader"
            assert response.params[0] == pytest.approx(0.72)

            await loop.sock_sendto(client, packet("/xremote"), address)
            await loop.sock_sendto(
                client, packet("/ch/01/config/name", "UDP integration test"), address
            )
            data, _peer = await asyncio.wait_for(
                loop.sock_recvfrom(client, 4096), timeout=1
            )
            update = OscMessage(data)
            assert update.address == "/ch/01/config/name"
            assert update.params == ["UDP integration test"]
            assert state.channels[1].name == "UDP integration test"
        finally:
            client.close()
            await simulator.stop()

    asyncio.run(exercise())
