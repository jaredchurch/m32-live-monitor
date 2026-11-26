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


def test_simulator_identity_responses_match_console_protocol():
    simulator = Simulator(ConsoleState(), name="Test-M32", model="M32",
                          firmware="4.06", server_version="V2.07")
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/info"))
    info = OscMessage(simulator.transport.sent[-1][0])
    assert info.address == "/info"
    assert info.params == ["V2.07", "osc-server", "M32", "4.06"]

    simulator.handle(client, packet("/xinfo"))
    xinfo = OscMessage(simulator.transport.sent[-1][0])
    assert xinfo.address == "/xinfo"
    assert xinfo.params == ["127.0.0.1", "Test-M32", "M32", "4.06"]

    simulator.handle(client, packet("/status"))
    status = OscMessage(simulator.transport.sent[-1][0])
    assert status.address == "/status"
    assert status.params == ["active", "127.0.0.1", "Test-M32"]


def test_simulator_unsubscribe_is_handled():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/xremote"))
    assert client in simulator.clients
    simulator.handle(client, packet("/unsubscribe"))

    assert client not in simulator.clients
    assert simulator.snapshot(outcome="handled_unsubscription")["events"]


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


def test_simulator_records_unhandled_get_and_response_traffic():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/ch/01/mix/fader"))
    simulator.handle(client, packet("/foo/not-implemented"))

    events = simulator.snapshot()["events"]
    assert any(e["outcome"] == "get_response" and e["address"] == "/ch/01/mix/fader" for e in events)
    unknown = [e for e in events if e["outcome"] == "unhandled_get"]
    assert len(unknown) == 1
    assert unknown[0]["address"] == "/foo/not-implemented"
    assert unknown[0]["peer"] == "127.0.0.1:50123"


def test_simulator_records_unhandled_set_and_argument_types():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/foo/not-implemented", 1.0))
    event = simulator.snapshot(outcome="unhandled_set")["events"][0]
    assert event["address"] == "/foo/not-implemented"
    assert event["args"][0]["type"] == "float"
    assert "No simulator state handler" in event["detail"]


def test_simulator_records_malformed_packets():
    simulator = Simulator(ConsoleState())
    simulator.handle(("127.0.0.1", 50123), b"not an OSC packet")
    events = simulator.snapshot()["events"]
    assert events[-1]["outcome"] == "malformed"
    assert events[-1]["direction"] == "in"


def test_simulator_log_filter_and_clear():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/info"))
    simulator.handle(client, packet("/missing/address"))

    filtered = simulator.snapshot(direction="out")
    assert all(event["direction"] == "out" for event in filtered["events"])
    assert filtered["counts"]["unhandled_get"] == 1
    simulator.clear_events()
    assert simulator.snapshot()["events"] == []


def test_scenario_presets_create_useful_channel_states():
    from m32_monitor.scenarios import apply_scenario, list_scenarios

    state = ConsoleState()
    selected = apply_scenario(state, "service")
    assert selected["id"] == "service"
    assert state.channels[1].name == "W1 - Lead Vocal"
    assert state.channels[1].connected is True
    assert state.channels[32].connected is False

    apply_scenario(state, "mute-test")
    assert state.channels[2].muted is True
    assert state.dcas[2]["on"] is False
    assert state.mute_groups[1] is True
    assert len(list_scenarios()) == 4


def test_unknown_scenario_is_rejected():
    from m32_monitor.scenarios import apply_scenario

    with pytest.raises(ValueError):
        apply_scenario(ConsoleState(), "not-a-scenario")



def test_batchsubscribe_returns_protocol_meter_blob():
    import struct

    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/batchsubscribe", "meters/0", "/meters/0", 0, 0, 1))

    event = simulator.snapshot(outcome="handled_batch_subscription")["events"][0]
    assert "70 values" in event["detail"]
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/meters/0"
    blob = response.params[0]
    assert isinstance(blob, bytes)
    assert struct.unpack(">I", blob[:4])[0] == len(blob) - 4
    assert struct.unpack("<I", blob[4:8])[0] == 70
    assert len(blob) == 8 + 70 * 4


def test_batchsubscribe_validates_meter_arguments():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/batchsubscribe", "alias", "/meters/6", 72, 0, 1))

    assert simulator.snapshot(outcome="unhandled_command")["events"][-1]["address"] == "/batchsubscribe"
    assert simulator.transport.sent == []


def test_node_get_returns_x32node_text_response():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "-prefs/rta/visibility"))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == ["/-prefs/rta/visibility 0\n"]
    assert simulator.snapshot(outcome="handled_node_get")["events"]


def test_rta_visibility_preference_can_be_read_and_updated():
    state = ConsoleState()
    assert state.get("/-prefs/rta/visibility") == 0
    assert state.update("/-prefs/rta/visibility", 7)
    assert state.get("/-prefs/rta/visibility") == 7


@pytest.mark.parametrize("path,first,second,count", [
    ("/meters/0", 0, 0, 70),
    ("/meters/2", 0, 0, 49),
    ("/meters/5", 3, 0, 27),
    ("/meters/6", 0, 0, 4),
    ("/meters/9", 0, 0, 32),
    ("/meters/10", 0, 0, 32),
    ("/meters/14", 0, 0, 80),
    ("/meters/16", 0, 0, 48),
])
def test_m32_edit_batchsubscribe_meter_stream_shapes(path, first, second, count):
    import struct

    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/batchsubscribe", path.lstrip("/"), path,
                                    first, second, 1))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == path
    blob = response.params[0]
    assert struct.unpack(">I", blob[:4])[0] == len(blob) - 4
    assert struct.unpack("<I", blob[4:8])[0] == count
    assert len(blob) == 8 + count * 4



def test_node_get_returns_rta_gain_x32node_response():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "-prefs/rta/gain"))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == ["/-prefs/rta/gain 0.0\n"]
    assert simulator.snapshot(outcome="handled_node_get")["events"]


def test_rta_gain_preference_can_be_read_and_updated():
    state = ConsoleState()
    assert state.get("/-prefs/rta/gain") == 0.0
    assert state.update("/-prefs/rta/gain", 18.0)
    assert state.get("/-prefs/rta/gain") == 18.0
    assert not state.update("/-prefs/rta/gain", 17.0)
    assert not state.update("/-prefs/rta/gain", 66.0)


def test_node_get_returns_rta_autogain_x32node_response():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "-prefs/rta/autogain"))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == ["/-prefs/rta/autogain 0\n"]
    assert simulator.snapshot(outcome="handled_node_get")["events"]


def test_rta_autogain_preference_can_be_read_and_updated():
    state = ConsoleState()
    assert state.get("/-prefs/rta/autogain") == 0
    assert state.update("/-prefs/rta/autogain", 1)
    assert state.get("/-prefs/rta/autogain") == 1
    assert state.update("/-prefs/rta/autogain", 0)
    assert not state.update("/-prefs/rta/autogain", 2)
