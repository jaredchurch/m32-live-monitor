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


def test_config_talk_node_groups_return_shared_and_a_b_settings():
    state = ConsoleState()
    state.talk_config.update({"enable": 1, "source": 1})
    state.talk_config["A"].update({"level": -12.5, "dim": 1, "latch": 0, "destmap": 0x20001})
    state.talk_config["B"].update({"level": 3.75, "dim": 0, "latch": 1, "destmap": 0x15555})
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    for header, expected in (
        ("config/talk", "/config/talk ON EXT\\n"),
        ("config/talk/A", "/config/talk/A -12.5 ON OFF %100000000000000001\\n"),
        ("config/talk/B", "/config/talk/B 3.8 OFF ON %010101010101010101\\n"),
    ):
        simulator.handle(client, packet("/node", header))
        response = OscMessage(simulator.transport.sent[-1][0])
        assert response.address == "/node"
        assert response.params == [expected]


@pytest.mark.parametrize("field,value", [
    ("enable", 1), ("source", 1),
    ("A/level", -90.0), ("A/level", 10.0), ("A/dim", 1),
    ("A/latch", 1), ("A/destmap", 262143),
    ("B/level", -12.5), ("B/dim", 0), ("B/latch", 0), ("B/destmap", 0),
])
def test_config_talk_individual_fields_can_be_read_and_set(field, value):
    state = ConsoleState()
    address = "/config/talk/" + field
    assert state.get(address) is not None
    assert state.update(address, value)
    assert state.get(address) == value


@pytest.mark.parametrize("address,value", [
    ("/config/talk/enable", 2), ("/config/talk/source", -1),
    ("/config/talk/A/dim", 2), ("/config/talk/B/latch", 0.5),
    ("/config/talk/A/level", 10.1), ("/config/talk/B/level", -90.1),
    ("/config/talk/A/level", -12.3), ("/config/talk/B/destmap", 262144),
    ("/config/talk/A/unknown", 1),
])
def test_config_talk_rejects_invalid_values(address, value):
    state = ConsoleState()
    assert not state.update(address, value)


def test_talkback_node_set_updates_shared_and_channel_settings_atomically():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/", "config/talk ON EXT"))
    assert simulator.state.talk_config["enable"] == 1
    assert simulator.state.talk_config["source"] == 1
    simulator.handle(client, packet("/", "config/talk/A -12.5 ON OFF %100000000000000001"))
    assert simulator.state.talk_config["A"] == {
        "level": -12.5, "dim": 1, "latch": 0, "destmap": 0x20001
    }
    before = dict(simulator.state.talk_config["A"])
    simulator.handle(client, packet("/", "config/talk/A -12.3 ON OFF %100000000000000001"))
    assert simulator.state.talk_config["A"] == before
    assert simulator.snapshot(outcome="unhandled_set")["events"]


def test_individual_talkback_node_get_returns_enum_and_bitmap_values():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.state.talk_config["A"].update({"dim": 1, "destmap": 5})
    for header, expected in (
        ("config/talk/enable", "/config/talk/enable OFF\\n"),
        ("config/talk/source", "/config/talk/source INT\\n"),
        ("config/talk/A/dim", "/config/talk/A/dim ON\\n"),
        ("config/talk/A/destmap", "/config/talk/A/destmap %000000000000000101\\n"),
    ):
        simulator.handle(client, packet("/node", header))
        response = OscMessage(simulator.transport.sent[-1][0])
        assert response.params == [expected]


def test_config_linkcfg_node_returns_four_link_preferences():
    state = ConsoleState()
    state.link_config.update({"hadly": 1, "eq": 0, "dyn": 1, "fdrmute": 1})
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "config/linkcfg"))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == ["/config/linkcfg ON OFF ON ON\n"]
    assert simulator.snapshot(outcome="handled_node_get")["events"]


def test_config_linkcfg_individual_get_set_and_validation():
    state = ConsoleState()
    assert state.get("/config/linkcfg/hadly") == 0
    assert state.update("/config/linkcfg/hadly", 1)
    assert state.get("/config/linkcfg/hadly") == 1
    assert not state.update("/config/linkcfg/hadly", 2)
    assert not state.update("/config/linkcfg/unknown", 1)
    assert not state.update("/config/linkcfg/eq", True)


def test_config_mono_node_returns_mode_and_link_settings():
    state = ConsoleState()
    state.mono_config.update({"mode": 1, "link": 1})
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "config/mono"))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == [
        "/config/mono/mode LCR\n/config/mono/link ON\n"
    ]
    assert simulator.snapshot(outcome="handled_node_get")["events"]


def test_config_mono_individual_get_set_and_validation():
    state = ConsoleState()
    assert state.get("/config/mono/mode") == 0
    assert state.get("/config/mono/link") == 0
    assert state.update("/config/mono/mode", 1)
    assert state.update("/config/mono/link", 1)
    assert state.get("/config/mono/mode") == 1
    assert state.get("/config/mono/link") == 1
    assert not state.update("/config/mono/mode", 2)
    assert not state.update("/config/mono/link", True)
    assert not state.update("/config/mono/unknown", 1)


def test_config_mute_node_returns_all_six_group_states():
    state = ConsoleState()
    state.mute_groups[1] = True
    state.mute_groups[4] = True
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "config/mute"))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == [
        "/config/mute/1 ON\n"
        "/config/mute/2 OFF\n"
        "/config/mute/3 OFF\n"
        "/config/mute/4 ON\n"
        "/config/mute/5 OFF\n"
        "/config/mute/6 OFF\n"
    ]
    assert simulator.snapshot(outcome="handled_node_get")["events"]


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
    assert response.params == ["/-prefs/rta/visibility OFF\n"]
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
    assert response.params == ["/-prefs/rta/gain 0.000000\n"]
    assert simulator.snapshot(outcome="handled_node_get")["events"]


def test_rta_gain_preference_can_be_read_and_updated():
    state = ConsoleState()
    assert state.get("/-prefs/rta/gain") == 0.0
    assert state.update("/-prefs/rta/gain", 0.3)
    assert state.get("/-prefs/rta/gain") == pytest.approx(0.3)
    assert not state.update("/-prefs/rta/gain", 0.31)
    assert not state.update("/-prefs/rta/gain", 1.1)


def test_node_get_returns_rta_autogain_x32node_response():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "-prefs/rta/autogain"))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == ["/-prefs/rta/autogain OFF\n"]
    assert simulator.snapshot(outcome="handled_node_get")["events"]


def test_rta_autogain_preference_can_be_read_and_updated():
    state = ConsoleState()
    assert state.get("/-prefs/rta/autogain") == 0
    assert state.update("/-prefs/rta/autogain", 1)
    assert state.get("/-prefs/rta/autogain") == 1
    assert state.update("/-prefs/rta/autogain", 0)
    assert not state.update("/-prefs/rta/autogain", 2)


def test_node_get_returns_rta_source_and_keysolo():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "-prefs/rta/source"))
    source = OscMessage(simulator.transport.sent[-1][0])
    assert source.address == "/node"
    assert source.params == ["/-prefs/rta/source 0" + chr(10)]

    simulator.handle(client, packet("/node", "-stat/keysolo"))
    keysolo = OscMessage(simulator.transport.sent[-1][0])
    assert keysolo.address == "/node"
    assert keysolo.params == ["/-stat/keysolo 0" + chr(10)]


def test_rta_source_and_keysolo_state_are_readable_and_validated():
    state = ConsoleState()
    assert state.get("/-prefs/rta/source") == 0
    assert state.update("/-prefs/rta/source", 73)
    assert state.get("/-prefs/rta/source") == 73
    assert not state.update("/-prefs/rta/source", 74)
    assert state.get("/-stat/keysolo") == 0
    assert state.update("/-stat/keysolo", 1)
    assert state.get("/-stat/keysolo") == 1
    assert not state.update("/-stat/keysolo", 2)


def test_showdump_returns_documented_empty_show_node():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/showdump"))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == ['/-showfile/show "" 0 0 0 0 0 0 0 0 0 "4.06"']
    assert simulator.snapshot(outcome="handled_showdump")["events"]


def test_formatsubscribe_handles_multiple_groups_and_packs_values():
    import struct

    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    args = [
        "states/prefs",
        "/-stat/tape/state", "/-usb/path/", "/-usb/title",
        "/-stat/tape/etime", "/-stat/tape/rtime",
        "/-stat/aes50/state", "/-stat/aes50/A", "/-stat/aes50/B",
        "/-prefs/clockrate", "/-prefs/clocksource", "/-show/prepos/current",
        "/-stat/usbmounted", "/-usb/dir/dirpos", "/-usb/dir/maxpos",
        "/-stat/xcardtype", "/-prefs/card/UFifc", "/-prefs/card/UFmode",
        0, 0, 0,
        "states/solo", "/-stat/solosw/**", 0, 0, 0,
    ]

    simulator.handle(client, packet("/formatsubscribe", *args))

    assert len(simulator.transport.sent) == 2
    prefs = OscMessage(simulator.transport.sent[0][0])
    assert prefs.address == "/states/prefs"
    prefs_blob = prefs.params[0]
    assert isinstance(prefs_blob, bytes)
    assert struct.unpack("<I", prefs_blob[:4])[0] == len(prefs_blob) - 4 == 180
    assert prefs_blob[4:8] == struct.pack("<i", 0)
    assert prefs_blob[8:40] == bytes(32)

    solo = OscMessage(simulator.transport.sent[1][0])
    assert solo.address == "/states/solo"
    solo_blob = solo.params[0]
    assert isinstance(solo_blob, bytes)
    assert struct.unpack("<I", solo_blob[:4])[0] == len(solo_blob) - 4 == 320
    assert struct.unpack("<80i", solo_blob[4:]) == (0,) * 80
    assert simulator.snapshot(outcome="handled_format_subscription")["events"]


def test_formatsubscribe_rejects_malformed_group_without_sending():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/formatsubscribe", "alias", "/ch/**/mix/on", 1))

    assert simulator.transport.sent == []
    assert simulator.snapshot(outcome="unhandled_command")["events"]


def test_node_get_returns_card_preferences():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "-prefs/card"))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == ["/-prefs/card " + " ".join(["0"] * 13) + chr(10)]


def test_snapshot_can_filter_only_protocol_exceptions():
    simulator = Simulator(ConsoleState())
    simulator.record("in", "handled_get", "/ch/01/mix/fader")
    simulator.record("in", "unhandled_get", "/mystery/path", detail="Unknown address")
    simulator.record("in", "unhandled_set", "/formatsubscribe", detail="Bad format")
    simulator.record("in", "malformed", detail="Invalid OSC packet")
    simulator.record("out", "send_error", "/ch/01/mix/fader", detail="UDP send failed")
    simulator.record("system", "scenario_loaded", detail="basic")

    result = simulator.snapshot(limit=2000, exceptions_only=True)

    assert [event["outcome"] for event in result["events"]] == [
        "unhandled_get", "unhandled_set", "malformed", "send_error"
    ]
    assert result["event_count"] == 6
    assert result["retained_events"] == 6


def test_exception_filter_can_be_combined_with_search():
    simulator = Simulator(ConsoleState())
    simulator.record("in", "unhandled_get", "/mystery/path", detail="Unknown address")
    simulator.record("in", "unhandled_set", "/formatsubscribe", detail="Bad format")

    result = simulator.snapshot(exceptions_only=True, search="format")

    assert len(result["events"]) == 1
    assert result["events"][0]["outcome"] == "unhandled_set"


def test_node_get_returns_rta_position_x32node_response():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "-prefs/rta/pos"))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == ["/-prefs/rta/pos PRE" + chr(10)]
    assert simulator.snapshot(outcome="handled_node_get")["events"]


def test_rta_position_preference_can_be_read_and_updated():
    state = ConsoleState()
    assert state.get("/-prefs/rta/pos") == 0
    assert state.update("/-prefs/rta/pos", 1)
    assert state.get("/-prefs/rta/pos") == 1
    assert state.update("/-prefs/rta/pos", 0)
    assert not state.update("/-prefs/rta/pos", 2)
    assert not state.update("/-prefs/rta/pos", 1.5)


def test_node_get_returns_rta_mode_x32node_response():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "-prefs/rta/mode"))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == ["/-prefs/rta/mode BAR" + chr(10)]
    assert simulator.snapshot(outcome="handled_node_get")["events"]


def test_rta_mode_preference_can_be_read_and_updated():
    state = ConsoleState()
    assert state.get("/-prefs/rta/mode") == 0
    assert state.update("/-prefs/rta/mode", 1)
    assert state.get("/-prefs/rta/mode") == 1
    assert state.update("/-prefs/rta/mode", 0)
    assert not state.update("/-prefs/rta/mode", 2)
    assert not state.update("/-prefs/rta/mode", 1.5)


def test_rta_options_preference_bitmask_can_be_read_and_updated():
    state = ConsoleState()
    assert state.get("/-prefs/rta/options") == 0
    assert state.update("/-prefs/rta/options", 0x21)
    assert state.get("/-prefs/rta/options") == 0x21
    assert state.update("/-prefs/rta/options", 0x3F)
    assert not state.update("/-prefs/rta/options", 0x40)
    assert not state.update("/-prefs/rta/options", 1.5)


def test_node_get_returns_rta_options_x32node_response():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "-prefs/rta/options"))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == ["/-prefs/rta/options %000000" + chr(10)]


@pytest.mark.parametrize("path,value", [
    ("/-prefs/rta/det", 1),
    ("/-prefs/rta/peakhold", 8),
    ("/-prefs/rta/options", 33),
    ("/-prefs/rta/option", 33),
    ("/-stat/rtamodeeq", 1),
    ("/-stat/rtamodegeq", 1),
    ("/-stat/rtaeqpre", 1),
    ("/-stat/rtageqpost", 1),
    ("/-stat/rtasource", 170),
])
def test_rta_integer_preferences_and_status_are_node_readable(path, value):
    state = ConsoleState()
    assert state.update(path, value)
    assert state.get(path) == value

    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/node", path.lstrip("/")))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    expected_value = {"/-prefs/rta/det": "PEAK", "/-prefs/rta/peakhold": "8", "/-prefs/rta/options": "%100001", "/-prefs/rta/option": "%100001", "/-stat/rtamodeeq": "SPEC", "/-stat/rtamodegeq": "SPEC", "/-stat/rtaeqpre": "ON", "/-stat/rtageqpost": "ON"}.get(path, str(value))
    assert response.params == [f"{path} {expected_value}\n"]


@pytest.mark.parametrize("path,value", [
    ("/-prefs/rta/det", 2),
    ("/-prefs/rta/peakhold", 9),
    ("/-prefs/rta/options", 64),
    ("/-stat/rtamodeeq", 2),
    ("/-stat/rtamodegeq", -1),
    ("/-stat/rtaeqpre", 2),
    ("/-stat/rtageqpost", -1),
    ("/-stat/rtasource", 171),
])
def test_rta_integer_preferences_and_status_reject_out_of_range_values(path, value):
    assert not ConsoleState().update(path, value)


@pytest.mark.parametrize("value,expected", [
    (0.0, 0.0), (1 / 18, 0.0556), (0.5, 0.5), (1.0, 1.0),
])
def test_rta_decay_uses_documented_normalised_log_steps(value, expected):
    state = ConsoleState()
    assert state.update("/-prefs/rta/decay", value)
    assert state.get("/-prefs/rta/decay") == pytest.approx(expected)


def test_rta_decay_rejects_values_outside_documented_curve():
    state = ConsoleState()
    assert not state.update("/-prefs/rta/decay", -0.1)
    assert not state.update("/-prefs/rta/decay", 1.1)
    assert not state.update("/-prefs/rta/decay", 0.2)


def test_node_get_returns_rta_decay_as_float():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/node", "-prefs/rta/decay"))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.params == ["/-prefs/rta/decay 0.000000\n"]


def test_rta_group_node_returns_all_ten_fields_in_console_format():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/node", "-prefs/rta"))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == ["/-prefs/rta OFF 0 OFF 0 PRE BAR %000000 RMS 0.25 OFF\n"]


@pytest.mark.parametrize("header,value,expected", [
    ("-prefs/rta/visibility", 3, "/-prefs/rta/visibility 35%\n"),
    ("-prefs/rta/autogain", 1, "/-prefs/rta/autogain ON\n"),
    ("-prefs/rta/pos", 1, "/-prefs/rta/pos POST\n"),
    ("-prefs/rta/mode", 1, "/-prefs/rta/mode SPEC\n"),
    ("-prefs/rta/det", 1, "/-prefs/rta/det PEAK\n"),
    ("-prefs/rta/peakhold", 8, "/-prefs/rta/peakhold 8\n"),
    ("-prefs/rta/options", 33, "/-prefs/rta/options %100001\n"),
    ("-stat/rtamodeeq", 1, "/-stat/rtamodeeq SPEC\n"),
    ("-stat/rtaeqpre", 1, "/-stat/rtaeqpre ON\n"),
])
def test_rta_node_enum_and_bitmap_responses_match_console_format(header, value, expected):
    state = ConsoleState()
    address = "/" + header
    assert state.update(address, value)
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    simulator.handle(("127.0.0.1", 50123), packet("/node", header))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.params == [expected]


def test_rta_node_group_set_updates_all_ten_preferences():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/", "-prefs/rta 35% 18 ON 12 POST SPEC %100001 PEAK 2.00 4"))
    p = simulator.state.preferences
    assert p["rta/visibility"] == 3
    assert p["rta/gain"] == pytest.approx(0.3)
    assert p["rta/autogain"] == 1
    assert p["rta/source"] == 12
    assert p["rta/pos"] == 1
    assert p["rta/mode"] == 1
    assert p["rta/options"] == 33
    assert p["rta/det"] == 1
    assert p["rta/decay"] == pytest.approx(0.5)
    assert p["rta/peakhold"] == 4
    assert simulator.snapshot(outcome="handled_node_set")["events"]


def test_rta_single_node_set_updates_enum_and_decay_values():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/", "-prefs/rta/mode SPEC"))
    simulator.handle(client, packet("/", "-prefs/rta/decay 2.00"))
    assert simulator.state.get("/-prefs/rta/mode") == 1
    assert simulator.state.get("/-prefs/rta/decay") == pytest.approx(0.5)


def test_rta_gain_uses_normalized_osc_float_steps():
    state = ConsoleState()
    assert state.update("/-prefs/rta/gain", 0.3)
    assert state.get("/-prefs/rta/gain") == pytest.approx(0.3)
    assert not state.update("/-prefs/rta/gain", 0.31)
    assert not state.update("/-prefs/rta/gain", 1.1)


def test_invalid_rta_group_node_set_is_atomic():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    before = dict(simulator.state.preferences)
    simulator.handle(client, packet("/", "-prefs/rta 35% 18 ON 12 POST SPEC %100001 PEAK 0.20 4"))
    assert simulator.state.preferences == before
    assert simulator.snapshot(outcome="unhandled_set")["events"]


def test_node_get_returns_xlive_urec_group():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "-urec"))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == [
        '/-urec 0 0 0 0 0 NONE 0 0 0 0 NONE NONE "Insert SD Card." "Insert SD Card." "" 0\n'
    ]
    assert simulator.snapshot(outcome="handled_node_get")["events"]


@pytest.mark.parametrize("header,value", [
    ("-urec/sessionmax", 3),
    ("-urec/markermax", 2),
    ("-urec/sessionlen", 3600000),
    ("-urec/sessionpos", 1),
    ("-urec/markerpos", 2),
    ("-urec/batterystate", 1),
    ("-urec/srate", 1),
    ("-urec/tracks", 32),
    ("-urec/sessionspan", 1),
    ("-urec/sessionoffs", 120000),
    ("-urec/sd1state", 1),
    ("-urec/sd2state", 3),
    ("-urec/errorcode", 12),
])
def test_xlive_urec_scalar_state_is_readable(header, value):
    state = ConsoleState()
    state.urec[header.rsplit("/", 1)[-1]] = value
    assert state.get("/" + header) == value


def test_xlive_urec_status_values_are_readable():
    state = ConsoleState()
    state.urec_status.update({"state": 3, "etime": 1500, "rtime": 2500})
    assert state.get("/-stat/urec/state") == 3
    assert state.get("/-stat/urec/etime") == 1500
    assert state.get("/-stat/urec/rtime") == 2500


@pytest.mark.parametrize("header,expected", [
    ("-urec/batterystate", "/-urec/batterystate NONE\n"),
    ("-urec/sd1state", "/-urec/sd1state NONE\n"),
    ("-urec/sd2info", '/-urec/sd2info "Insert SD Card."\n'),
    ("-urec/session/001/name", '/-urec/session/001/name ""\n'),
    ("-urec/marker/001/time", "/-urec/marker/001/time 0\n"),
    ("-stat/urec/state", "/-stat/urec/state STOP\n"),
])
def test_xlive_urec_individual_node_values(header, expected):
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    simulator.handle(("127.0.0.1", 50123), packet("/node", header))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == [expected]


@pytest.mark.parametrize("family,pairs", [
    ("chlink", 16), ("auxlink", 4), ("fxlink", 4),
    ("buslink", 8), ("mtxlink", 3),
])
def test_config_link_node_returns_all_pair_states(family, pairs):
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "config/" + family))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    lines = response.params[0].strip().splitlines()
    assert len(lines) == pairs
    assert all(line.endswith(" OFF") for line in lines)
    assert simulator.snapshot(outcome="handled_node_get")["events"]


def test_config_link_parameters_can_be_read_and_set():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/config/chlink/1-2"))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/config/chlink/1-2"
    assert response.params == [0]

    simulator.handle(client, packet("/config/chlink/1-2", 1))
    assert state.get("/config/chlink/1-2") == 1
    assert state.update("/config/buslink/1-2", 1)
    assert state.get("/config/buslink/1-2") == 1


def test_config_link_rejects_unknown_pair_and_invalid_value():
    state = ConsoleState()
    assert not state.update("/config/chlink/2-3", 1)
    assert not state.update("/config/chlink/1-2", 2)
    assert "/config/chlink/2-3" not in state.routing.values
    assert "/config/chlink/1-2" not in state.routing.values


@pytest.mark.parametrize("value", [2, -1, 0.5, float("nan"), True, "1", None])
def test_routing_inventory_rejects_non_binary_stereo_link_values(value):
    state = ConsoleState()
    assert not state.routing.update("/config/chlink/1-2", value)
    assert not state.update("/config/chlink/1-2", value)
    assert "/config/chlink/1-2" not in state.routing.values



def test_config_solo_node_returns_all_seventeen_fields_in_protocol_order():
    state = ConsoleState()
    state.solo_config.update({
        "level": -12.5, "source": 2, "sourcetrim": 1.5,
        "chmode": 1, "busmode": 0, "dcamode": 1,
        "exclusive": 1, "followsel": 0, "followsolo": 1,
        "dimatt": -18.0, "dim": 1, "mono": 0, "delay": 1,
        "delaytime": 125.5, "masterctrl": 1, "mute": 0, "dimpfl": 1,
    })
    simulator = Simulator(state)
    simulator.transport = FakeTransport()

    simulator.handle(("127.0.0.1", 50123), packet("/node", "config/solo"))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == [
        "/config/solo -12.5 LR+C 1.5 AFL PFL AFL ON OFF ON -18.0 ON OFF ON 125.5 ON OFF ON\n"
    ]
    assert simulator.snapshot(outcome="handled_node_get")["events"]


@pytest.mark.parametrize("field,value", [
    ("level", -90.0), ("level", 10.0), ("source", 6),
    ("sourcetrim", -18.0), ("sourcetrim", 18.0),
    ("chmode", 1), ("busmode", 1), ("dcamode", 1),
    ("exclusive", 1), ("followsel", 1), ("followsolo", 1),
    ("dimatt", -40.0), ("dimatt", 0.0), ("dim", 1), ("mono", 1),
    ("delay", 1), ("delaytime", 0.3), ("delaytime", 500.0),
    ("masterctrl", 1), ("mute", 1), ("dimpfl", 1),
])
def test_config_solo_fields_can_be_read_and_set(field, value):
    state = ConsoleState()
    address = "/config/solo/" + field
    assert state.get(address) == state.solo_config[field]
    assert state.update(address, value)
    assert state.get(address) == value


@pytest.mark.parametrize("field,value", [
    ("source", 7), ("chmode", 2), ("exclusive", True),
    ("sourcetrim", 0.25), ("dimatt", -40.5),
    ("delaytime", 0.35), ("delaytime", 500.1), ("level", 10.625),
])
def test_config_solo_fields_reject_invalid_values(field, value):
    assert not ConsoleState().update("/config/solo/" + field, value)


def test_config_osc_node_returns_all_six_fields_in_protocol_order():
    state = ConsoleState()
    state.osc_config.update({"level": -12.5, "f1": 2000.0, "f2": 632.456,
                             "fsel": 1, "type": 2, "dest": 24})
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    simulator.handle(("127.0.0.1", 50123), packet("/node", "config/osc"))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == ["/config/osc -12.5 2000.000 632.456 F2 WHITE 24\\n"]


@pytest.mark.parametrize("field,value", [
    ("level", -90.0), ("level", 10.0), ("f1", 20.0), ("f1", 20000.0),
    ("f2", 2000.0), ("fsel", 1), ("type", 2), ("dest", 25),
])
def test_config_osc_fields_can_be_read_and_set(field, value):
    state = ConsoleState()
    address = "/config/osc/" + field
    assert state.get(address) is not None
    assert state.update(address, value)
    assert state.get(address) == value


@pytest.mark.parametrize("field,value", [
    ("level", 10.1), ("level", -90.1), ("level", -12.3),
    ("f1", 19.9), ("f1", 20001.0), ("f1", 1001.0),
    ("f2", 0), ("fsel", 2), ("type", 3), ("dest", 26),
    ("dest", 1.5), ("type", True), ("unknown", 1),
])
def test_config_osc_rejects_invalid_values(field, value):
    assert not ConsoleState().update("/config/osc/" + field, value)


def test_config_osc_individual_node_get_uses_enum_labels():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.state.osc_config.update({"fsel": 1, "type": 2, "dest": 25})
    for header, expected in (
        ("config/osc/fsel", "/config/osc/fsel F2\\n"),
        ("config/osc/type", "/config/osc/type WHITE\\n"),
        ("config/osc/dest", "/config/osc/dest 25\\n"),
    ):
        simulator.handle(client, packet("/node", header))
        response = OscMessage(simulator.transport.sent[-1][0])
        assert response.params == [expected]


def test_config_osc_node_set_updates_all_fields_atomically():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/", "config/osc -12.5 2000 632.456 F2 WHITE 24"))
    assert simulator.state.osc_config == {
        "level": -12.5, "f1": 2000.0, "f2": 632.456,
        "fsel": 1, "type": 2, "dest": 24,
    }
    before = dict(simulator.state.osc_config)
    simulator.handle(client, packet("/", "config/osc -12.3 2000 632.456 F2 WHITE 24"))
    assert simulator.state.osc_config == before
    assert simulator.snapshot(outcome="unhandled_set")["events"]


def test_config_osc_individual_node_set_updates_enum_and_numeric_values():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/", "config/osc/fsel F2"))
    simulator.handle(client, packet("/", "config/osc/type PINK"))
    simulator.handle(client, packet("/", "config/osc/dest 25"))
    assert simulator.state.osc_config["fsel"] == 1
    assert simulator.state.osc_config["type"] == 1
    assert simulator.state.osc_config["dest"] == 25
