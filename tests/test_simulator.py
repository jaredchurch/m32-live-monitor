import pytest
import shlex
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
        ("config/talk", "/config/talk ON EXT\n"),
        ("config/talk/A", "/config/talk/A -12.5 ON OFF %100000000000000001\n"),
        ("config/talk/B", "/config/talk/B 3.8 OFF ON %010101010101010101\n"),
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


def test_individual_talkback_node_get_returns_enum_and_bitmap_values():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.state.talk_config["A"].update({"dim": 1, "destmap": 5})
    for header, expected in (
        ("config/talk/enable", "/config/talk/enable OFF\n"),
        ("config/talk/source", "/config/talk/source INT\n"),
        ("config/talk/A/dim", "/config/talk/A/dim ON\n"),
        ("config/talk/A/destmap", "/config/talk/A/destmap %000000000000000101\n"),
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
                client, packet("/ch/01/config/name", "UDP test"), address
            )
            data, _peer = await asyncio.wait_for(
                loop.sock_recvfrom(client, 4096), timeout=1
            )
            update = OscMessage(data)
            assert update.address == "/ch/01/config/name"
            assert update.params == ["UDP test"]
            assert state.channels[1].name == "UDP test"
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


def test_node_set_updates_all_card_preferences():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    values = list(range(13))

    simulator.handle(client, packet("/", "-prefs/card " + " ".join(map(str, values))))

    assert list(state.card_preferences.values()) == values
    assert simulator.snapshot(outcome="handled_node_set")["events"]


def test_node_set_card_preferences_rejects_wrong_count_atomically():
    state = ConsoleState()
    simulator = Simulator(state)
    before = dict(state.card_preferences)
    simulator.handle(("127.0.0.1", 50123), packet("/", "-prefs/card 1 2"))
    assert state.card_preferences == before
    assert simulator.snapshot(outcome="unhandled_set")["events"]


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
    expected_value = {"/-prefs/rta/det": "PEAK", "/-prefs/rta/peakhold": "8s", "/-prefs/rta/options": "%100001", "/-prefs/rta/option": "%100001", "/-stat/rtamodeeq": "SPEC", "/-stat/rtamodegeq": "SPEC", "/-stat/rtaeqpre": "ON", "/-stat/rtageqpost": "ON"}.get(path, str(value))
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
    ("-prefs/rta/peakhold", 8, "/-prefs/rta/peakhold 8s\n"),
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
    simulator.handle(client, packet("/", "-prefs/rta 35% 18 ON 12 POST SPEC %100001 PEAK 2.00 4s"))
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


@pytest.mark.parametrize("header,value,expected", [
    ("-urec/sessionmax", "12", 12),
    ("-urec/batterystate", "GOOD", 1),
    ("-urec/sd1state", "READY", 1),
    ("-urec/sd1info", '"Card ready"', "Card ready"),
    ("-urec/errormessage", '"No error"', "No error"),
])
def test_xlive_urec_individual_node_set(header, value, expected):
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    simulator.handle(("127.0.0.1", 50123), packet("/", header + " " + value))
    assert state.get(header) == expected
    assert simulator.snapshot(outcome="handled_node_set")["events"]


@pytest.mark.parametrize("field,value,expected", [
    ("on", "OFF", 0), ("fader", "0.25", 0.25),
    ("config/name", '"Vox DCA"', "Vox DCA"), ("config/icon", "12", 12),
    ("config/color", "GN", 2),
])
def test_dca_individual_node_get_set(field, value, expected):
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/", "dca/1/%s %s" % (field, value)))
    assert state.get("/dca/1/" + field) == expected
    simulator.handle(client, packet("/node", "dca/1/" + field))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params
    assert simulator.snapshot(outcome="handled_node_get")["events"]


@pytest.mark.parametrize("tokens,expected", [
    ("0 0 0 0 0 NONE 0 0 0 0 NONE NONE \"\" \"\" \"\" 0",
     [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "", "", "", 0]),
    ("1 2 3 4 5 GOOD 6 7 8 9 READY ERROR \"Card one\" \"Card two\" \"No error\" 10",
     [1, 2, 3, 4, 5, 1, 6, 7, 8, 9, 1, 3, "Card one", "Card two", "No error", 10]),
])
def test_xlive_urec_group_set_updates_all_fields(tokens, expected):
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/", "-urec " + tokens))
    assert list(simulator.state.urec.values()) == expected
    assert simulator.snapshot(outcome="handled_node_set")["events"]


def test_xlive_urec_group_set_rejects_invalid_enum_atomically():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    before = dict(simulator.state.urec)
    simulator.handle(("127.0.0.1", 50123), packet("/", "-urec 1 2 3 4 5 INVALID 6 7 8 9 NONE NONE \"\" \"\" \"\" 0"))
    assert simulator.state.urec == before
    assert simulator.snapshot(outcome="unhandled_set")["events"]


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


@pytest.mark.parametrize("family,pairs", [
    ("chlink", 16), ("auxlink", 4), ("fxlink", 4),
    ("buslink", 8), ("mtxlink", 3),
])
def test_config_link_group_set_updates_all_pairs(family, pairs):
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    tokens = ["ON" if index in (2, pairs - 1) else "OFF" for index in range(pairs)]

    simulator.handle(client, packet("/", "config/%s %s" % (family, " ".join(tokens))))

    assert list(state.config_links[family].values()) == [1 if token == "ON" else 0 for token in tokens]
    assert simulator.snapshot(outcome="handled_node_set")["events"]


def test_config_link_group_set_rejects_wrong_count_and_invalid_enum_atomically():
    state = ConsoleState()
    simulator = Simulator(state)
    before = dict(state.config_links["chlink"])
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/", "config/chlink OFF ON"))
    assert state.config_links["chlink"] == before
    simulator.handle(client, packet("/", "config/chlink " + " ".join(["OFF"] * 15 + ["INVALID"])))
    assert state.config_links["chlink"] == before
    assert len(simulator.snapshot(outcome="unhandled_set")["events"]) == 2


@pytest.mark.parametrize("header,payload,expected", [
    ("config/linkcfg", "ON OFF ON OFF", [1, 0, 1, 0]),
    ("config/mono", "LCR ON", [1, 1]),
    ("config/solo", "0 LR 0 PFL AFL PFL ON OFF ON -20 OFF ON OFF 10 ON OFF ON",
     [0.0, 1, 0.0, 0, 1, 0, 1, 0, 1, -20.0, 0, 1, 0, 10.0, 1, 0, 1]),
    ("config/mute", "OFF ON OFF ON OFF ON", [0, 1, 0, 1, 0, 1]),
])
def test_configuration_group_sets_update_all_fields(header, payload, expected):
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/", header + " " + payload))

    if header == "config/linkcfg":
        actual = list(state.link_config.values())
    elif header == "config/mono":
        actual = list(state.mono_config.values())
    elif header == "config/solo":
        actual = list(state.solo_config.values())
    else:
        actual = [int(value) for value in state.mute_groups.values()]
    assert actual == expected
    assert simulator.snapshot(outcome="handled_node_set")["events"]


@pytest.mark.parametrize("header,payload", [
    ("config/linkcfg", "ON OFF"),
    ("config/mono", "INVALID ON"),
    ("config/solo", "0 LR 0 PFL AFL PFL ON OFF ON -20 OFF ON OFF 10 ON OFF INVALID"),
    ("config/mute", "OFF ON OFF"),
])
def test_configuration_group_sets_reject_invalid_payloads_atomically(header, payload):
    state = ConsoleState()
    simulator = Simulator(state)
    before = {
        "config/linkcfg": dict(state.link_config),
        "config/mono": dict(state.mono_config),
        "config/solo": dict(state.solo_config),
        "config/mute": dict(state.mute_groups),
    }[header]
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/", header + " " + payload))

    after = {
        "config/linkcfg": state.link_config,
        "config/mono": state.mono_config,
        "config/solo": state.solo_config,
        "config/mute": state.mute_groups,
    }[header]
    assert after == before
    assert simulator.snapshot(outcome="unhandled_set")["events"]


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


@pytest.mark.parametrize("address,value", [
    ("/config/routing/IN/1-8", 24),
    ("/config/routing/AES50A/1-8", 36),
    ("/config/routing/OUT/1-4", 36),
    ("/config/routing/routswitch", 2),
    ("/config/routing/rootswitch", -1),
    ("/config/routing/IN/AUX", 16),
    ("/config/routing/IN/1-8", 1.5),
    ("/config/routing/IN/1-8", True),
])
def test_routing_enum_values_are_validated_against_protocol(address, value):
    assert not ConsoleState().update(address, value)


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
    assert response.params == ["/config/osc -12.5 2000.000 632.456 F2 WHITE 24\n"]


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
    ("f1", 19.9), ("f1", 20001.0),
    ("f2", 0), ("fsel", 2), ("type", 3), ("dest", 26),
    ("dest", 1.5), ("type", True), ("unknown", 1),
])
def test_config_osc_rejects_invalid_values(field, value):
    assert not ConsoleState().update("/config/osc/" + field, value)


def test_config_osc_accepts_frequency_values_outside_nominal_slider_grid():
    state = ConsoleState()
    assert state.update("/config/osc/f1", 1000.0)
    assert state.get("/config/osc/f1") == 1000.0


def test_config_osc_individual_node_get_uses_enum_labels():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.state.osc_config.update({"fsel": 1, "type": 2, "dest": 25})
    for header, expected in (
        ("config/osc/fsel", "/config/osc/fsel F2\n"),
        ("config/osc/type", "/config/osc/type WHITE\n"),
        ("config/osc/dest", "/config/osc/dest 25\n"),
    ):
        simulator.handle(client, packet("/node", header))
        response = OscMessage(simulator.transport.sent[-1][0])
        assert response.params == [expected]


@pytest.mark.parametrize("token,expected", [
    ("1k00", 1000.0), ("2k50", 2500.0), ("20k00", 20000.0), ("632.456", 632.456),
])
def test_oscillator_frequency_parser_accepts_console_khz_notation(token, expected):
    from m32_monitor.simulator import _parse_osc_frequency
    assert _parse_osc_frequency(token) == pytest.approx(expected)


def test_config_osc_group_set_accepts_console_khz_notation():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/", "config/osc -40.0 1k00 2k50 F1 WHITE 18"))
    assert simulator.state.osc_config["level"] == -40.0
    assert simulator.state.osc_config["f1"] == 1000.0
    assert simulator.state.osc_config["f2"] == 2500.0
    assert simulator.state.osc_config["dest"] == 18
    assert simulator.snapshot(outcome="handled_node_set")["events"]


def test_config_osc_individual_frequency_set_accepts_console_khz_notation():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    simulator.handle(("127.0.0.1", 50123), packet("/", "config/osc/f1 1k00"))
    assert simulator.state.osc_config["f1"] == 1000.0
    assert simulator.snapshot(outcome="handled_node_set")["events"]


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


@pytest.mark.parametrize("header", [
    "config/routing/routswitch",
    "config/routing/rootswitch",
    "config/routing/outswitch",
])
def test_routing_switch_node_spellings_return_a_valid_response(header):
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    simulator.handle(("127.0.0.1", 50123), packet("/node", header))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params[0].splitlines() == ["/" + header + " REC"]


def test_config_routing_parent_node_returns_all_documented_routing_entries():
    from m32_monitor.routing import ROUTING_PATHS

    state = ConsoleState()
    state.routing.update("/config/routing/IN/1-8", 3)
    state.routing.update("/config/routing/AES50A/1-8", 5)
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "config/routing"))

    response = OscMessage(simulator.transport.sent[-1][0])
    lines = response.params[0].splitlines()
    assert response.address == "/node"
    assert len(lines) == len(ROUTING_PATHS) - 1
    assert "/config/routing/IN/1-8 AN25-32" in lines
    assert "/config/routing/AES50A/1-8 A9-16" in lines
    assert "/config/routing/outswitch REC" in lines
    assert simulator.snapshot(outcome="handled_node_get")["events"]


@pytest.mark.parametrize("header,expected", [
    ("config/routing/IN", 5),
    ("config/routing/AES50A", 6),
    ("config/routing/AES50B", 6),
    ("config/routing/CARD", 4),
    ("config/routing/OUT", 4),
    ("config/routing/PLAY", 5),
])
def test_config_routing_bank_nodes_return_their_documented_entries(header, expected):
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    simulator.handle(("127.0.0.1", 50123), packet("/node", header))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert len(response.params[0].splitlines()) == expected


@pytest.mark.parametrize("bank,token,colour", [("B", "GN", 2), ("C", "RD", 1)])
def test_userctrl_bank_parent_node_set_accepts_colour_only_write(bank, token, colour):
    state = ConsoleState()
    state.update("/config/userctrl/%s/enc/1" % bank, "F00")
    state.update("/config/userctrl/%s/btn/5" % bank, "MN05003")
    simulator = Simulator(state)
    simulator.transport = FakeTransport()

    # X32node SETs are sent to the root address, not the /node GET endpoint.
    simulator.handle(("127.0.0.1", 50123),
                     packet("/", "config/userctrl/%s %s" % (bank, token)))

    assert state.get("/config/userctrl/%s/color" % bank) == colour
    assert state.get("/config/userctrl/%s/enc/1" % bank) == "F00"
    assert state.get("/config/userctrl/%s/btn/5" % bank) == "MN05003"
    assert simulator.snapshot(outcome="unhandled_set")["events"] == []


def test_userctrl_bank_parent_address_accepts_colour_only_osc_set():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/config/userctrl/C", "RD"))

    assert state.get("/config/userctrl/C/color") == 1
    event = simulator.snapshot(outcome="handled_set")["events"][-1]
    assert event["address"] == "/config/userctrl/C"
    assert simulator.snapshot(outcome="unhandled_set")["events"] == []


@pytest.mark.parametrize("token", ["INVALID", "16", ""])
def test_userctrl_bank_parent_address_rejects_invalid_colour_token(token):
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()

    simulator.handle(("127.0.0.1", 50123), packet("/config/userctrl/C", token))

    assert state.get("/config/userctrl/C/color") == 0
    assert simulator.snapshot(outcome="unhandled_set")["events"]


def test_userctrl_bank_nodes_return_color_encoders_and_buttons():
    state = ConsoleState()
    state.update("/config/userctrl/A/color", 3)
    state.update("/config/userctrl/A/enc/1", "F00")
    state.update("/config/userctrl/A/btn/5", "MN05003")
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "config/userctrl/A"))
    lines = OscMessage(simulator.transport.sent[-1][0]).params[0].splitlines()
    assert len(lines) == 13
    assert lines[0] == "/config/userctrl/A/color YE"
    assert lines[1] == "/config/userctrl/A/enc/1 F00"
    assert lines[5] == "/config/userctrl/A/btn/5 MN05003"

    simulator.handle(client, packet("/node", "config/userctrl/B/enc"))
    lines = OscMessage(simulator.transport.sent[-1][0]).params[0].splitlines()
    assert len(lines) == 4
    simulator.handle(client, packet("/node", "config/userctrl/C/btn"))
    lines = OscMessage(simulator.transport.sent[-1][0]).params[0].splitlines()
    assert len(lines) == 8


@pytest.mark.parametrize("address,value", [
    ("/config/userctrl/A/color", 15),
    ("/config/userctrl/B/enc/4", "F79"),
    ("/config/userctrl/C/btn/12", "MN60127"),
    ("/config/tape/gainL", 12.5),
    ("/config/tape/gainR", -6.0),
    ("/config/tape/autoplay", 1),
    ("/config/amixenable/X", 1),
    ("/config/amixenable/Y", 0),
    ("/config/dp48/scope", 15),
    ("/config/dp48/aesAB", 1),
    ("/config/dp48/link/24", 1),
    ("/config/dp48/assign/48", 12),
    ("/config/dp48/grpname/12", "Choir"),
])
def test_extended_configuration_values_can_be_read_and_set(address, value):
    state = ConsoleState()
    assert state.update(address, value)
    assert state.get(address) == value


def test_dp48_broadcast_is_a_one_shot_command():
    state = ConsoleState()
    assert state.update("/config/dp48/broadcast", 1)
    assert state.get("/config/dp48/broadcast") == 0


@pytest.mark.parametrize("address,value", [
    ("/config/userctrl/A/color", 16),
    ("/config/userctrl/A/enc/5", "F00"),
    ("/config/userctrl/A/enc/1", "TOO-LONG"),
    ("/config/userctrl/A/btn/4", "MN05003"),
    ("/config/tape/gainL", 24.5),
    ("/config/tape/gainR", 0.25),
    ("/config/tape/autoplay", 2),
    ("/config/amixenable/Z", 1),
    ("/config/dp48/scope", 16),
    ("/config/dp48/broadcast", 2),
    ("/config/dp48/link/25", 1),
    ("/config/dp48/assign/01", 13),
    ("/config/dp48/grpname/01", "TOO-LONG!!"),
])
def test_extended_configuration_rejects_out_of_spec_values(address, value):
    assert not ConsoleState().update(address, value)


def test_tape_amix_and_dp48_node_groups_return_documented_entries():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    for header, count in (("config/tape", 3), ("config/amixenable", 2),
                          ("config/dp48", 87), ("config/dp48/link", 24),
                          ("config/dp48/assign", 48), ("config/dp48/grpname", 12)):
        simulator.handle(client, packet("/node", header))
        response = OscMessage(simulator.transport.sent[-1][0])
        assert response.address == "/node"
        assert len(response.params[0].splitlines()) == count


def test_extended_configuration_x32node_writes_update_state():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/", "config/userctrl/A " + " ".join(["YE", "F00", "P01", "S0000", "X0000", "MN05003"] + ["-"] * 7)))
    assert simulator.state.get("/config/userctrl/A/color") == 3
    assert simulator.state.get("/config/userctrl/A/enc/1") == "F00"
    assert simulator.state.get("/config/userctrl/A/btn/5") == "MN05003"

    simulator.handle(client, packet("/", "config/tape 12.0 -3.5 ON"))
    assert simulator.state.tape_config == {"gainL": 12.0, "gainR": -3.5, "autoplay": 1}

    simulator.handle(client, packet("/", "config/amixenable ON OFF"))
    assert simulator.state.amix_enable == {"X": 1, "Y": 0}

    simulator.handle(client, packet("/", "config/dp48 %1010 1 AESB"))
    assert simulator.state.dp48_config["scope"] == 10
    assert simulator.state.dp48_config["broadcast"] == 0
    assert simulator.state.dp48_config["aesAB"] == 1

    simulator.handle(client, packet("/", "config/dp48/link " + " ".join(["1"] + ["0"] * 23)))
    assert simulator.state.dp48_config["link"][1] == 1
    simulator.handle(client, packet("/", "config/dp48/assign " + " ".join(["12"] + ["0"] * 47)))
    assert simulator.state.dp48_config["assign"][1] == 12
    simulator.handle(client, packet("/", "config/dp48/grpname " + " ".join(["Choir"] + ["G"] * 11)))
    assert simulator.state.dp48_config["grpname"][1] == "Choir"
    assert simulator.snapshot(outcome="handled_node_set")["events"]


def test_extended_configuration_individual_node_reads_render_enums_and_bitmaps():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.state.update("/config/userctrl/B/color", 15)
    simulator.state.update("/config/amixenable/X", 1)
    simulator.state.update("/config/dp48/scope", 10)
    for header, expected in (
        ("config/userctrl/B/color", "/config/userctrl/B/color WHi\n"),
        ("config/amixenable/X", "/config/amixenable/X ON\n"),
        ("config/dp48/scope", "/config/dp48/scope %1010\n"),
    ):
        simulator.handle(client, packet("/node", header))
        response = OscMessage(simulator.transport.sent[-1][0])
        assert response.params == [expected]


def test_userrout_out_node_returns_all_48_slots_in_order():
    state = ConsoleState()
    state.user_rout_out.update({1: 1, 8: 167, 48: 208})
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/node", "config/userrout/out"))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    lines = response.params[0].splitlines()
    assert len(lines) == 48
    assert lines[0] == "/config/userrout/out/01 1"
    assert lines[7] == "/config/userrout/out/08 167"
    assert lines[-1] == "/config/userrout/out/48 208"
    assert simulator.snapshot(outcome="handled_node_get")["events"]


@pytest.mark.parametrize("slot,value", [(1, 1), (16, 80), (32, 168)])
def test_userrout_in_individual_values_can_be_read_and_set(slot, value):
    state = ConsoleState()
    address = "/config/userrout/in/%02d" % slot
    assert state.get(address) == 0
    assert state.update(address, value)
    assert state.get(address) == value


def test_userrout_in_node_returns_all_32_slots_in_order():
    state = ConsoleState()
    state.user_rout_in.update({1: 1, 16: 80, 32: 168})
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/node", "config/userrout/in"))
    response = OscMessage(simulator.transport.sent[-1][0])
    lines = response.params[0].splitlines()
    assert len(lines) == 32
    assert lines[0] == "/config/userrout/in/01 1"
    assert lines[15] == "/config/userrout/in/16 80"
    assert lines[-1] == "/config/userrout/in/32 168"


@pytest.mark.parametrize("address,value", [
    ("/config/userrout/in/00", 1), ("/config/userrout/in/33", 1),
    ("/config/userrout/in/1", 1), ("/config/userrout/in/01", -1),
    ("/config/userrout/in/01", 169), ("/config/userrout/in/01", 1.5),
    ("/config/userrout/in/01", True),
])
def test_userrout_in_rejects_invalid_slots_and_sources(address, value):
    assert not ConsoleState().update(address, value)


@pytest.mark.parametrize("slot,value", [(1, 0), (8, 167), (48, 208)])
def test_userrout_out_individual_values_can_be_read_and_set(slot, value):
    state = ConsoleState()
    address = "/config/userrout/out/%02d" % slot
    assert state.get(address) == 0
    assert state.update(address, value)
    assert state.get(address) == value


@pytest.mark.parametrize("address,value", [
    ("/config/userrout/out/00", 1), ("/config/userrout/out/49", 1),
    ("/config/userrout/out/1", 1), ("/config/userrout/out/01", -1),
    ("/config/userrout/out/01", 209), ("/config/userrout/out/01", 1.5),
    ("/config/userrout/out/01", True),
])
def test_userrout_out_rejects_invalid_slots_and_sources(address, value):
    assert not ConsoleState().update(address, value)


def test_userrout_out_individual_node_get_and_set():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/", "config/userrout/out/08 167"))
    assert simulator.state.get("/config/userrout/out/08") == 167
    simulator.handle(client, packet("/node", "config/userrout/out/08"))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.params == ["/config/userrout/out/08 167\n"]
    assert simulator.snapshot(outcome="handled_node_set")["events"]

@pytest.mark.parametrize("direction,count,maximum", [("out", 48, 208), ("in", 32, 168)])
def test_userrout_parent_node_set_applies_complete_mapping_atomically(direction, count, maximum):
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    values = [0] * count
    values[0] = 1
    values[-1] = maximum
    simulator.handle(client, packet("/", "config/userrout/%s " % direction + " ".join(map(str, values))))
    slots = state.user_rout_out if direction == "out" else state.user_rout_in
    assert list(slots.values()) == values
    assert simulator.snapshot(outcome="handled_node_set")["events"]


@pytest.mark.parametrize("direction,count,maximum", [("out", 48, 208), ("in", 32, 168)])
def test_userrout_direct_bulk_osc_set_applies_complete_mapping(direction, count, maximum):
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    values = [0] * count
    values[0] = 1
    values[-1] = maximum
    simulator.handle(client, packet("/config/userrout/" + direction, *values))
    slots = state.user_rout_out if direction == "out" else state.user_rout_in
    assert list(slots.values()) == values
    assert simulator.snapshot(outcome="handled_set")["events"]


@pytest.mark.parametrize("direction,count,maximum", [("out", 48, 208), ("in", 32, 168)])
def test_userrout_bulk_sets_reject_wrong_count_or_invalid_source_without_partial_write(direction, count, maximum):
    for invalid_values in ([0] * (count - 1), [0] * (count - 1) + [maximum + 1]):
        state = ConsoleState()
        simulator = Simulator(state)
        simulator.transport = FakeTransport()
        client = ("127.0.0.1", 50123)
        before = dict(state.user_rout_out if direction == "out" else state.user_rout_in)
        simulator.handle(client, packet("/config/userrout/" + direction, *invalid_values))
        assert (state.user_rout_out if direction == "out" else state.user_rout_in) == before
        assert simulator.snapshot(outcome="unhandled_set")["events"]


def test_routing_input_node_set_accepts_m32_edit_symbolic_enum_names():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    tokens = ["UIN1-8", "UIN9-16", "UIN17-24", "UIN25-32", "AUX1-4"]
    simulator.handle(client, packet("/", "config/routing/IN " + " ".join(tokens)))
    from m32_monitor.routing import ROUTING_ENUM_TOKENS
    paths = ["/config/routing/IN/1-8", "/config/routing/IN/9-16",
             "/config/routing/IN/17-24", "/config/routing/IN/25-32",
             "/config/routing/IN/AUX"]
    assert [state.routing.get(path) for path in paths] == [
        ROUTING_ENUM_TOKENS[path].index(token) for path, token in zip(paths, tokens)]
    assert simulator.snapshot(outcome="handled_node_set")["events"]


@pytest.mark.parametrize("address,token,expected", [
    ("/config/routing/IN/1-8", "UIN1-8", 20),
    ("/config/routing/IN/AUX", "AUX1-4", 0),
    ("/config/routing/AES50A/1-8", "UOUT1-8", 26),
    ("/config/routing/OUT/1-4", "UIN1-4", 32),
    ("/config/routing/OUT/5-8", "UIN5-8", 32),
    ("/config/routing/PLAY/1-8", "CARD1-8", 16),
])
def test_individual_routing_osc_set_accepts_symbolic_enum_names(address, token, expected):
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    simulator.handle(("127.0.0.1", 50123), packet(address, token))
    assert simulator.state.routing.get(address) == expected


@pytest.mark.parametrize("header", [
    "config/routing", "config/routing/IN", "config/routing/AES50A",
    "config/routing/AES50B", "config/routing/CARD", "config/routing/OUT",
    "config/routing/PLAY",
])
def test_all_routing_group_nodes_accept_protocol_symbolic_tokens(header):
    from m32_monitor.routing import ROUTING_ENUM_TOKENS, ROUTING_PATHS

    prefix = "/" + header
    paths = [path for path in ROUTING_PATHS if path.startswith(prefix + "/")
             and path.rsplit("/", 1)[-1] not in ("routswitch", "rootswitch", "outswitch")]
    values = [ROUTING_ENUM_TOKENS[path][-1] for path in paths]
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    simulator.handle(("127.0.0.1", 50123),
                     packet("/", header + " " + " ".join(values)))
    assert [state.routing.get(path) for path in paths] == [
        len(ROUTING_ENUM_TOKENS[path]) - 1 for path in paths]
    assert simulator.snapshot(outcome="handled_node_set")["events"]


def test_routing_input_node_get_returns_symbolic_enum_names():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/", "config/routing/IN " +
                                    "UIN1-8 UIN9-16 UIN17-24 UIN25-32 AUX1-4"))
    simulator.handle(client, packet("/node", "config/routing/IN"))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert "UIN1-8" in response.params[0]
    assert "AUX1-4" in response.params[0]


@pytest.mark.parametrize("header", [
    "config/routing", "config/routing/IN", "config/routing/AES50A",
    "config/routing/AES50B", "config/routing/CARD", "config/routing/OUT",
    "config/routing/PLAY",
])
def test_routing_group_node_set_applies_ordered_patch_values(header):
    from m32_monitor.routing import ROUTING_PATHS

    prefix = "/" + header
    paths = [path for path in ROUTING_PATHS if path.startswith(prefix + "/")
             and path.rsplit("/", 1)[-1] not in ("routswitch", "rootswitch", "outswitch")]
    values = [0] * len(paths)
    values[-1] = len(ROUTING_PATHS[paths[-1]][1]) - 1
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/", header + " " + " ".join(map(str, values))))
    assert [state.routing.get(path) for path in paths] == values
    assert simulator.snapshot(outcome="handled_node_set")["events"]


@pytest.mark.parametrize("header", [
    "/config/routing", "/config/routing/IN", "/config/routing/AES50A",
    "/config/routing/AES50B", "/config/routing/CARD", "/config/routing/OUT",
    "/config/routing/PLAY",
])
def test_routing_group_direct_osc_set_applies_ordered_patch_values(header):
    from m32_monitor.routing import ROUTING_PATHS

    paths = [path for path in ROUTING_PATHS if path.startswith(header + "/")
             and path.rsplit("/", 1)[-1] not in ("routswitch", "rootswitch", "outswitch")]
    values = [0] * len(paths)
    values[-1] = len(ROUTING_PATHS[paths[-1]][1]) - 1
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet(header, *values))
    assert [state.routing.get(path) for path in paths] == values
    assert simulator.snapshot(outcome="handled_set")["events"]


def test_channel_config_parent_node_returns_identity_and_routing_fields():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "ch/01/config"))

    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == ['/ch/01/config "CH 01" 1 RD 1\n']
    assert simulator.snapshot(outcome="handled_node_get")["events"]


def test_channel_processing_node_reads_cover_delay_preamp_gate_dynamics_insert_and_eq():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    headers = (
        "ch/01/delay", "ch/01/preamp", "ch/01/gate", "ch/01/gate/filter",
        "ch/01/dyn", "ch/01/dyn/filter", "ch/01/insert", "ch/01/eq",
        "ch/01/eq/1", "ch/01/mix", "ch/01/mix/01", "ch/01/grp",
        "ch/01/automix",
    )
    expected_counts = (2, 5, 8, 3, 15, 3, 3, 1, 4, 6, 5, 2, 2)
    for header, count in zip(headers, expected_counts):
        simulator.handle(client, packet("/node", header))
        response = OscMessage(simulator.transport.sent[-1][0])
        assert response.address == "/node"
        assert len(response.params[0].split()) == count + 1
        assert response.params[0].startswith("/" + header + " ")


def test_channel_processing_node_group_writes_and_individual_access():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/", "ch/01/gate ON GATE -30 40 5 100 200 1"))
    simulator.handle(client, packet("/", "ch/01/eq/2 PEQ 1200 -2.5 1.4"))
    simulator.handle(client, packet("/", "ch/01/preamp 3.0 ON OFF 18 80"))

    assert simulator.state.get("/ch/01/gate/thr") == -30.0
    assert simulator.state.get("/ch/01/gate/mode") == 3
    assert simulator.state.get("/ch/01/eq/2/f") == 1200.0
    assert simulator.state.get("/ch/01/eq/2/g") == -2.5
    assert simulator.state.get("/ch/01/preamp/trim") == 3.0
    assert simulator.state.get("/ch/01/preamp/invert") == 1

    simulator.handle(client, packet("/node", "ch/01/gate/thr"))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == ["/ch/01/gate/thr -30.000\n"]
    assert simulator.snapshot(outcome="handled_node_set")["events"]


@pytest.mark.parametrize("header,expected_path", [
    ("ch/01/eq/4 HShv 9k35 -11.7 2.0", "/ch/01/eq/4/f"),
    ("ch/01/eq/4/f 9k35", "/ch/01/eq/4/f"),
    ("mtx/01/eq/6 HShv 9k35 -11.7 2.0", "/mtx/01/eq/6/f"),
])
def test_eq_frequency_node_writes_accept_compact_khz_notation(header, expected_path):
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()

    simulator.handle(("127.0.0.1", 50123), packet("/", header))

    assert state.get(expected_path) == 9350.0
    if " HShv " in header:
        assert state.get(expected_path.rsplit("/", 1)[0] + "/g") == -11.7
    assert simulator.snapshot(outcome="unhandled_set")["events"] == []


def test_auxin_and_fx_return_processing_nodes_match_supported_protocol_scope():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "auxin/01/preamp"))
    assert len(OscMessage(simulator.transport.sent[-1][0]).params[0].split()) == 3
    simulator.handle(client, packet("/node", "auxin/01/eq/4"))
    assert len(OscMessage(simulator.transport.sent[-1][0]).params[0].split()) == 5
    simulator.handle(client, packet("/node", "fxrtn/01/eq"))
    assert len(OscMessage(simulator.transport.sent[-1][0]).params[0].split()) == 2
    simulator.handle(client, packet("/node", "fxrtn/01/eq/1"))
    assert len(OscMessage(simulator.transport.sent[-1][0]).params[0].split()) == 5

    simulator.handle(client, packet("/", "auxin/01/preamp 4.0 ON"))
    simulator.handle(client, packet("/", "fxrtn/01/eq/1 HShv 8000 2.0 0.7"))
    assert simulator.state.get("/auxin/01/preamp/trim") == 4.0
    assert simulator.state.get("/fxrtn/01/eq/1/type") == 4
    assert simulator.state.get("/fxrtn/01/eq/1/f") == 8000.0


def test_channel_processing_node_writes_reject_invalid_groups_atomically():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/", "ch/01/gate ON GATE -30 40 5 100 200 65"))
    assert state.get("/ch/01/gate/on") == 0
    assert state.get("/ch/01/gate/thr") == -40.0
    assert simulator.snapshot(outcome="unhandled_set")["events"]

    assert not state.update("/ch/01/eq/1/g", 15.25)
    assert not state.update("/ch/01/preamp/trim", 18.25)
    assert not state.update("/ch/01/delay/time", 500.1)
    assert not state.update("/auxin/01/gate/on", 1)

 
def test_bus_config_parent_node_returns_name_icon_and_colour():
    state = ConsoleState()
    state.buses[1].update({"name": "Vocal Bus", "icon": 12, "colour": 3})
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/node", "bus/01/config"))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert response.params == ['/bus/01/config "Vocal Bus" 12 YE\n']
    assert simulator.snapshot(outcome="handled_node_get")["events"]


def test_bus_config_fields_can_be_read_and_set_with_validation():
    state = ConsoleState()
    assert state.get("/bus/01/config/icon") == 1
    assert state.get("/bus/01/config/color") == 1
    assert state.update("/bus/01/config/name", "Monitor")
    assert state.update("/bus/01/config/icon", 74)
    assert state.update("/bus/01/config/color", 15)
    assert state.get("/bus/01/config/name") == "Monitor"
    assert state.get("/bus/01/config/icon") == 74
    assert state.get("/bus/01/config/color") == 15
    assert not state.update("/bus/01/config/icon", 75)
    assert not state.update("/bus/01/config/color", 16)
    assert not state.update("/bus/01/config/name", "Name is too long")



def test_bus_dynamics_node_reads_and_writes_group_and_individual_fields():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/node", "bus/01/dyn"))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/node"
    assert len(response.params[0].split()) == 16
    assert response.params[0].startswith("/bus/01/dyn ")

    simulator.handle(client, packet("/", "bus/01/dyn ON COMP PEAK LIN -24 4.0 0 0 10 10 100 PRE 0 100 OFF"))
    assert simulator.state.get("/bus/01/dyn/on") == 1
    assert simulator.state.get("/bus/01/dyn/mode") == 0
    assert simulator.state.get("/bus/01/dyn/thr") == -24.0
    assert simulator.state.get("/bus/01/dyn/ratio") == 6
    assert simulator.state.get("/bus/01/dyn/auto") == 0

    simulator.handle(client, packet("/node", "bus/01/dyn/thr"))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.params == ["/bus/01/dyn/thr -24.000\n"]


def test_bus_dynamics_reject_invalid_values():
    state = ConsoleState()
    assert not state.update("/bus/01/dyn/thr", -60.25)
    assert not state.update("/bus/01/dyn/ratio", 12)
    assert not state.update("/bus/01/dyn/on", 2)


def test_matrix_config_processing_and_output_nodes_are_discoverable_and_writable():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    expected_counts = {
        "config": 3, "preamp": 1, "dyn": 14, "dyn/filter": 3,
        "insert": 3, "eq": 1, "eq/6": 4, "mix": 2, "grp": 2,
    }
    for matrix_number in range(1, 7):
        for node, count in expected_counts.items():
            header = "mtx/%02d/%s" % (matrix_number, node)
            simulator.handle(client, packet("/node", header))
            response = OscMessage(simulator.transport.sent[-1][0])
            assert response.address == "/node"
            assert len(shlex.split(response.params[0])) - 1 == count
            assert response.params[0].startswith("/" + header + " ")

    simulator.handle(client, packet("/", 'mtx/01/config "Vocal Matrix" 12 YE'))
    simulator.handle(client, packet("/", "mtx/01/preamp ON"))
    simulator.handle(client, packet("/", "mtx/01/dyn ON COMP RMS LIN -30 4.0 2 3 15 20 150 POST 75 OFF"))
    simulator.handle(client, packet("/", "mtx/01/dyn/filter ON HC12 120"))
    simulator.handle(client, packet("/", "mtx/01/insert ON POST FX3L"))
    simulator.handle(client, packet("/", "mtx/01/eq ON"))
    simulator.handle(client, packet("/", "mtx/01/eq/6 PEQ 2500 -3.0 1.2"))
    simulator.handle(client, packet("/", "mtx/01/mix OFF 0.65"))
    simulator.handle(client, packet("/", "mtx/01/grp 3 5"))

    assert state.get("/mtx/01/config/name") == "Vocal Matrix"
    assert state.get("/mtx/01/config/icon") == 12
    assert state.get("/mtx/01/config/color") == 3
    assert state.get("/mtx/01/preamp/invert") == 1
    assert state.get("/mtx/01/dyn/thr") == -30.0
    assert state.get("/mtx/01/dyn/ratio") == 6
    assert state.get("/mtx/01/dyn/filter/f") == 120.0
    assert state.get("/mtx/01/insert/sel") == 5
    assert state.get("/mtx/01/eq/6/type") == 2
    assert state.get("/mtx/01/eq/6/g") == -3.0
    assert state.get("/mtx/01/mix/on") == 0
    assert state.get("/mtx/01/mix/fader") == 0.65
    assert state.get("/mtx/01/grp/dca") == 3
    assert state.get("/mtx/01/grp/mute") == 5

    simulator.handle(client, packet("/node", "mtx/01/insert/sel"))
    assert OscMessage(simulator.transport.sent[-1][0]).params == ["/mtx/01/insert/sel FX3L\n"]


@pytest.mark.parametrize(("address", "value"), [
    ("/mtx/01/config/icon", 75), ("/mtx/01/config/color", 16),
    ("/mtx/01/preamp/invert", 2), ("/mtx/01/config/preamp/invert", 2), ("/mtx/01/dyn/thr", -60.25),
    ("/mtx/01/dyn/ratio", 12), ("/mtx/01/dyn/filter/f", 20001),
    ("/mtx/01/insert/sel", 23), ("/mtx/01/eq/6/type", 14),
    ("/mtx/01/eq/6/g", 15.25), ("/mtx/01/mix/fader", 1.1),
    ("/mtx/01/grp/mute", 64), ("/mtx/07/mix/on", 1),
])
def test_matrix_processing_rejects_invalid_values(address, value):
    assert not ConsoleState().update(address, value)


def test_main_output_config_and_processing_nodes_for_stereo_and_mono():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    expected = {"config": 3, "dyn": 15, "dyn/filter": 3, "insert": 3,
                "eq": 1, "eq/6": 4, "mix": 2, "grp": 2}
    for prefix in ("main/st", "main/m"):
        for node, count in expected.items():
            header = prefix + "/" + node
            simulator.handle(client, packet("/node", header))
            response = OscMessage(simulator.transport.sent[-1][0])
            assert response.address == "/node"
            assert len(shlex.split(response.params[0])) - 1 == count
            assert response.params[0].startswith("/" + header + " ")
        simulator.handle(client, packet("/", prefix + '/config "Main Out" 12 YE'))
        simulator.handle(client, packet("/", prefix + "/dyn ON COMP RMS LIN -30 4.0 2 3 15 20 150 POST 0 75 OFF"))
        simulator.handle(client, packet("/", prefix + "/dyn/filter ON HC12 120"))
        simulator.handle(client, packet("/", prefix + "/insert ON POST FX3L"))
        simulator.handle(client, packet("/", prefix + "/eq ON"))
        simulator.handle(client, packet("/", prefix + "/eq/6 PEQ 2500 -3.0 1.2"))
        simulator.handle(client, packet("/", prefix + "/mix OFF 0.65"))
        simulator.handle(client, packet("/", prefix + "/grp 3 5"))
        assert state.get("/" + prefix + "/config/name") == "Main Out"
        assert state.get("/" + prefix + "/config/icon") == 12
        assert state.get("/" + prefix + "/config/color") == 3
        assert state.get("/" + prefix + "/dyn/thr") == -30.0
        assert state.get("/" + prefix + "/dyn/filter/f") == 120.0
        assert state.get("/" + prefix + "/insert/sel") == 5
        assert state.get("/" + prefix + "/eq/6/g") == -3.0
        assert state.get("/" + prefix + "/mix/fader") == 0.65
        assert state.get("/" + prefix + "/grp/mute") == 5


def test_main_output_matrix_sends_are_discoverable_readable_and_writable():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    for prefix in ("main/st", "main/m"):
        for matrix in range(1, 7):
            header = "%s/mix/%02d" % (prefix, matrix)
            simulator.handle(client, packet("/node", header))
            response = OscMessage(simulator.transport.sent[-1][0])
            assert response.address == "/node"
            assert response.params == ["/%s ON 0.000\n" % header]

            simulator.handle(client, packet("/", header + " OFF 0.65"))
            assert state.get("/%s/on" % header) == 0
            assert state.get("/%s/level" % header) == 0.65
            output_key = "main_st" if prefix == "main/st" else "main_mono"
            assert state.outputs[output_key]["sends"][matrix] == {"on": 0, "level": 0.65}

            simulator.handle(client, packet("/node", header))
            response = OscMessage(simulator.transport.sent[-1][0])
            assert response.params == ["/%s OFF 0.650\n" % header]


@pytest.mark.parametrize(("address", "value"), [
    ("/main/st/mix/00/on", 1), ("/main/m/mix/07/level", 0.5),
    ("/main/st/mix/01/on", 2), ("/main/m/mix/06/level", 1.1),
])
def test_main_output_matrix_sends_reject_invalid_values(address, value):
    assert not ConsoleState().update(address, value)


@pytest.mark.parametrize(("address", "value"), [
    ("/main/st/config/icon", 75), ("/main/m/config/color", 16),
    ("/main/st/dyn/thr", -60.25), ("/main/m/insert/sel", 23),
    ("/main/st/eq/6/g", 15.25), ("/main/m/mix/fader", 1.1),
])

def test_main_output_processing_rejects_invalid_values(address, value):
    assert not ConsoleState().update(address, value)


def test_simulator_default_discovery_name_is_m32_simulation():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    simulator.handle(client, packet("/xinfo"))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.address == "/xinfo"
    assert response.params[1] == "M32-Simulation"


def test_bus_insert_eq_mix_and_group_nodes_are_discoverable_and_writable():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    expected_counts = {
        "insert": 3, "eq": 1, "eq/6": 4, "mix": 2,
        "mix/06": 2, "grp": 2,
    }
    for node, count in expected_counts.items():
        simulator.handle(client, packet("/node", "bus/01/" + node))
        response = OscMessage(simulator.transport.sent[-1][0])
        assert response.address == "/node"
        assert len(shlex.split(response.params[0])) - 1 == count
        assert response.params[0].startswith("/bus/01/" + node + " ")

    simulator.handle(client, packet("/", "bus/01/insert ON POST FX3L"))
    simulator.handle(client, packet("/", "bus/01/eq/6 PEQ 2500 -3.0 1.2"))
    simulator.handle(client, packet("/", "bus/01/mix ON 0.65"))
    simulator.handle(client, packet("/", "bus/01/mix/06 ON 0.50"))
    simulator.handle(client, packet("/", "bus/01/grp 3 5"))

    assert state.get("/bus/01/insert/on") == 1
    assert state.get("/bus/01/insert/pos") == 1
    assert state.get("/bus/01/insert/sel") == 5
    assert state.get("/bus/01/eq/6/type") == 2
    assert state.get("/bus/01/eq/6/f") == 2500.0
    assert state.get("/bus/01/eq/6/g") == -3.0
    assert state.get("/bus/01/mix/on") == 1
    assert state.get("/bus/01/mix/fader") == 0.65
    assert state.get("/bus/01/mix/06/on") == 1
    assert state.get("/bus/01/mix/06/level") == 0.5
    assert state.get("/bus/01/grp/dca") == 3
    assert state.get("/bus/01/grp/mute") == 5


def test_bus_insert_eq_and_matrix_send_validation():
    state = ConsoleState()
    assert not state.update("/bus/01/insert/sel", 23)
    assert not state.update("/bus/01/eq/6/g", 15.25)
    assert not state.update("/bus/01/mix/06/level", 1.1)
    assert not state.update("/bus/01/grp/mute", 64)


def test_all_eight_dca_nodes_and_config_nodes_are_discoverable_and_writable():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    colours = ("OFF", "RD", "GN", "YE", "BL", "MG", "CY", "WH",
               "OFFi", "RDi", "GNi", "YEi", "BLi", "MGi", "CYi", "WHi")

    for number in range(1, 9):
        simulator.handle(client, packet("/node", "dca/%d" % number))
        response = OscMessage(simulator.transport.sent[-1][0])
        assert response.address == "/node"
        lines = response.params[0].splitlines()
        assert len(lines) == 5
        assert lines[0] == "/dca/%d/on ON" % number
        assert lines[1] == "/dca/%d/fader 0.750" % number
        assert lines[2] == '/dca/%d/config/name "DCA %d"' % (number, number)
        assert lines[3] == "/dca/%d/config/icon 1" % number
        assert lines[4] == "/dca/%d/config/color RD" % number

        simulator.handle(client, packet("/node", "dca/%d/config" % number))
        response = OscMessage(simulator.transport.sent[-1][0])
        assert response.params == ['/dca/%d/config "DCA %d" 1 RD\n' % (number, number)]

        colour = colours[number + 1]
        simulator.handle(client, packet("/", 'dca/%d OFF 0.625 "Monitor %d" %d %s' %
                                        (number, number, number + 1, colour)))
        assert state.dcas[number] == {
            "number": number, "name": "Monitor %d" % number, "icon": number + 1,
            "colour": number + 1, "on": False, "fader": 0.625
        }

        simulator.handle(client, packet("/node", "dca/%d" % number))
        response = OscMessage(simulator.transport.sent[-1][0])
        assert response.params[0].splitlines() == [
            "/dca/%d/on OFF" % number, "/dca/%d/fader 0.625" % number,
            '/dca/%d/config/name "Monitor %d"' % (number, number),
            "/dca/%d/config/icon %d" % (number, number + 1),
            "/dca/%d/config/color %s" % (number, colour),
        ]


@pytest.mark.parametrize(("address", "value"), [
    ("/dca/1/on", 2), ("/dca/1/on", True), ("/dca/1/fader", 1.01),
    ("/dca/1/config/name", "Name is too long"),
    ("/dca/1/config/icon", 0), ("/dca/1/config/icon", 75),
    ("/dca/1/config/color", 16), ("/dca/9/on", 1),
])
def test_dca_individual_values_reject_invalid_inputs(address, value):
    assert not ConsoleState().update(address, value)


def test_dca_individual_values_can_be_read_and_set():
    state = ConsoleState()
    for number in range(1, 9):
        prefix = "/dca/%d/" % number
        for suffix, value in (("on", 0), ("fader", 0.625), ("config/name", "Monitor"),
                              ("config/icon", 74), ("config/color", 15)):
            address = prefix + suffix
            assert state.update(address, value)
            assert state.get(address) == value


def test_invalid_grouped_dca_node_write_is_rejected_without_partial_changes():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    before = dict(simulator.state.dcas[1])

    simulator.handle(client, packet("/", 'dca/1 OFF 0.625 "Changed" 0 YE'))

    assert simulator.state.dcas[1] == before
    assert simulator.snapshot(outcome="unhandled_set")["events"]


@pytest.mark.parametrize("number", range(1, 9))
def test_fx_slot_nodes_are_readable_and_writable(number):
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    type_count = 61 if number <= 4 else 34

    simulator.handle(client, packet("/node", "fx/%02d" % number))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.params == ["/fx/%02d/type HALL\n" % number] if number <= 4 else ["/fx/%02d/type GEQ2\n" % number]

    simulator.handle(client, packet("/fx/%02d/type" % number, type_count - 1))
    assert state.get("/fx/%02d/type" % number) == type_count - 1

    if number <= 4:
        simulator.handle(client, packet("/node", "fx/%02d/source" % number))
        assert OscMessage(simulator.transport.sent[-1][0]).params == ["/fx/%02d/source INS INS\n" % number]
        simulator.handle(client, packet("/", "fx/%02d/source MIX3 M/C" % number))
        assert state.get("/fx/%02d/source/l" % number) == 3
        assert state.get("/fx/%02d/source/r" % number) == 17
        simulator.handle(client, packet("/node", "fx/%02d/source/l" % number))
        assert OscMessage(simulator.transport.sent[-1][0]).params == ["/fx/%02d/source/l MIX3\n" % number]
    else:
        simulator.handle(client, packet("/node", "fx/%02d/source" % number))
        assert simulator.snapshot(outcome="unhandled_command")["events"]

    simulator.handle(client, packet("/fx/%02d/par/01" % number, 0.375))
    assert state.get("/fx/%02d/par/01" % number) == 0.375
    simulator.handle(client, packet("/node", "fx/%02d/par/01" % number))
    assert OscMessage(simulator.transport.sent[-1][0]).params == ["/fx/%02d/par/01 0.375000\n" % number]

    simulator.handle(client, packet("/node", "fx/%02d/par" % number))
    lines = OscMessage(simulator.transport.sent[-1][0]).params[0].splitlines()
    assert len(lines) == 64
    assert lines[0] == "/fx/%02d/par/01 0.375000" % number
    assert lines[-1] == "/fx/%02d/par/64 0.000000" % number


def test_fx_grouped_node_writes_and_invalid_values():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/", "fx/01 DLY"))
    assert state.get("/fx/01/type") == 10
    simulator.handle(client, packet("/", "fx/01/source MIX1 MIX2"))
    assert state.get("/fx/01/source/l") == 1
    assert state.get("/fx/01/source/r") == 2
    params = " ".join(["0.25"] * 64)
    simulator.handle(client, packet("/", "fx/01/par " + params))
    assert state.get("/fx/01/par/64") == 0.25

    assert not state.update("/fx/01/type", 61)
    assert not state.update("/fx/05/type", 34)
    assert not state.update("/fx/05/source/l", 1)
    assert not state.update("/fx/01/source/r", 18)
    assert not state.update("/fx/01/par/65", 0.5)
    assert not state.update("/fx/01/par/01", float("inf"))



def test_physical_main_output_nodes_are_discoverable_readable_and_writable():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    for number in range(1, 17):
        prefix = "outputs/main/%02d" % number
        simulator.handle(client, packet("/node", prefix))
        response = OscMessage(simulator.transport.sent[-1][0])
        assert response.params == [
            "/%s/src 0\n/%s/pos POST\n/%s/invert OFF\n" % (prefix, prefix, prefix)
        ]
        simulator.handle(client, packet("/node", prefix + "/delay"))
        response = OscMessage(simulator.transport.sent[-1][0])
        assert response.params == ["/%s/delay/on OFF\n/%s/delay/time 0.3\n" % (prefix, prefix)]

    simulator.handle(client, packet("/", "outputs/main/01 18 PRE ON"))
    assert state.get("/outputs/main/01/src") == 18
    assert state.get("/outputs/main/01/pos") == 6
    assert state.get("/outputs/main/01/invert") == 1
    simulator.handle(client, packet("/", "outputs/main/01/delay ON 125.5"))
    assert state.get("/outputs/main/01/delay/on") == 1
    assert state.get("/outputs/main/01/delay/time") == 125.5

    simulator.handle(client, packet("/", "outputs/main/01/delay/on ON"))
    simulator.handle(client, packet("/", "outputs/main/01/delay/time 12.3"))
    assert state.get("/outputs/main/01/delay/on") == 1
    assert state.get("/outputs/main/01/delay/time") == 12.3
    simulator.handle(client, packet("/", "outputs/main/01/pos EQ->"))
    assert state.get("/outputs/main/01/pos") == 4

    simulator.handle(client, packet("/node", "outputs/main/01/src"))
    assert OscMessage(simulator.transport.sent[-1][0]).params == ["/outputs/main/01/src 18\n"]
    simulator.handle(client, packet("/node", "outputs/main/01/delay/time"))
    assert OscMessage(simulator.transport.sent[-1][0]).params == ["/outputs/main/01/delay/time 12.3\n"]

    simulator.handle(client, packet("/outputs/main/02/src", 76))
    assert state.get("/outputs/main/02/src") == 76
    simulator.handle(client, packet("/outputs/main/02/pos", 0))
    assert state.get("/outputs/main/02/pos") == 0


@pytest.mark.parametrize(("address", "value"), [
    ("/outputs/main/01/src", 77), ("/outputs/main/17/src", 1),
    ("/outputs/main/01/pos", 9), ("/outputs/main/01/invert", 2),
    ("/outputs/main/01/delay/on", -1),
    ("/outputs/main/01/delay/time", 0.2),
    ("/outputs/main/01/delay/time", 500.1),
    ("/outputs/main/01/delay/time", 1.05),
    ("/outputs/main/01/unknown", 1),
])
def test_physical_main_output_state_rejects_invalid_values(address, value):
    assert not ConsoleState().update(address, value)


def test_invalid_physical_main_output_node_write_is_atomic():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    before = dict(simulator.state.output_main[1])
    simulator.handle(client, packet("/", "outputs/main/01 77 PRE ON"))
    assert simulator.state.output_main[1] == before
    assert simulator.snapshot(outcome="unhandled_set")["events"]


@pytest.mark.parametrize("number", range(1, 7))
def test_physical_aux_output_node_get_set_and_direct_osc(number):
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    prefix = "outputs/aux/%02d" % number

    simulator.handle(client, packet("/node", prefix))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.params == [
        "/%s/src 0\n/%s/pos POST\n/%s/invert OFF\n" % (prefix, prefix, prefix)
    ]

    simulator.handle(client, packet("/", prefix + " 33 PRE ON"))
    assert state.get("/" + prefix + "/src") == 33
    assert state.get("/" + prefix + "/pos") == 6
    assert state.get("/" + prefix + "/invert") == 1

    simulator.handle(client, packet("/node", prefix + "/src"))
    assert OscMessage(simulator.transport.sent[-1][0]).params == ["/%s/src 33\n" % prefix]
    simulator.handle(client, packet("/outputs/aux/%02d/pos" % number, 0))
    assert state.get("/" + prefix + "/pos") == 0


@pytest.mark.parametrize(("address", "value"), [
    ("/outputs/aux/01/src", 77), ("/outputs/aux/07/src", 1),
    ("/outputs/aux/01/pos", 9), ("/outputs/aux/01/invert", 2),
    ("/outputs/aux/01/delay/on", 1), ("/outputs/aux/01/unknown", 1),
])
def test_physical_aux_output_rejects_invalid_values(address, value):
    assert not ConsoleState().update(address, value)


def test_invalid_physical_aux_output_node_write_is_atomic():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    before = dict(simulator.state.output_aux[1])
    simulator.handle(client, packet("/", "outputs/aux/01 77 PRE ON"))
    assert simulator.state.output_aux[1] == before
    assert simulator.snapshot(outcome="unhandled_set")["events"]


@pytest.mark.parametrize("number", range(1, 17))
def test_p16_output_node_get_set_and_iq_configuration(number):
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    prefix = "outputs/p16/%02d" % number

    simulator.handle(client, packet("/node", prefix))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.params == ["/%s/src 0\n/%s/pos POST\n" % (prefix, prefix)]

    simulator.handle(client, packet("/", prefix + " 33 PRE"))
    assert state.get("/" + prefix + "/src") == 33
    assert state.get("/" + prefix + "/pos") == 6

    simulator.handle(client, packet("/node", prefix + "/iQ"))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.params == ["/%s/iQ/group OFF\n/%s/iQ/speaker none\n" % (prefix, prefix)]

    simulator.handle(client, packet("/", prefix + "/iQ A iQ12"))
    assert state.get("/" + prefix + "/iQ/group") == 1
    assert state.get("/" + prefix + "/iQ/speaker") == 3

    simulator.handle(client, packet("/node", prefix + "/iQ/group"))
    assert OscMessage(simulator.transport.sent[-1][0]).params == ["/%s/iQ/group A\n" % prefix]
    simulator.handle(client, packet("/outputs/p16/%02d/src" % number, 12))
    assert state.get("/" + prefix + "/src") == 12


@pytest.mark.parametrize(("address", "value"), [
    ("/outputs/p16/01/src", 77), ("/outputs/p16/17/src", 1),
    ("/outputs/p16/01/pos", 9), ("/outputs/p16/01/iQ/group", 3),
    ("/outputs/p16/01/iQ/speaker", 7), ("/outputs/p16/01/invert", 1),
])
def test_p16_output_rejects_invalid_values(address, value):
    assert not ConsoleState().update(address, value)


def test_invalid_p16_output_node_write_is_atomic():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    before = dict(simulator.state.output_p16[1])
    simulator.handle(client, packet("/", "outputs/p16/01 77 PRE"))
    assert simulator.state.output_p16[1] == before
    assert simulator.snapshot(outcome="unhandled_set")["events"]


@pytest.mark.parametrize("number", range(1, 3))
def test_aes_output_node_get_set_and_direct_osc(number):
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    prefix = "outputs/aes/%02d" % number

    simulator.handle(client, packet("/node", prefix))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.params == [
        "/%s/src 0\n/%s/pos POST\n/%s/invert OFF\n" % (prefix, prefix, prefix)
    ]

    simulator.handle(client, packet("/", prefix + " 33 PRE ON"))
    assert state.get("/" + prefix + "/src") == 33
    assert state.get("/" + prefix + "/pos") == 6
    assert state.get("/" + prefix + "/invert") == 1

    simulator.handle(client, packet("/node", prefix + "/invert"))
    assert OscMessage(simulator.transport.sent[-1][0]).params == ["/%s/invert ON\n" % prefix]
    simulator.handle(client, packet("/outputs/aes/%02d/src" % number, 12))
    assert state.get("/" + prefix + "/src") == 12


@pytest.mark.parametrize("number", range(1, 3))
def test_recording_output_node_get_set_and_direct_osc(number):
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    prefix = "outputs/rec/%02d" % number

    simulator.handle(client, packet("/node", prefix))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.params == ["/%s/src 0\n/%s/pos POST\n" % (prefix, prefix)]

    simulator.handle(client, packet("/", prefix + " 33 PRE"))
    assert state.get("/" + prefix + "/src") == 33
    assert state.get("/" + prefix + "/pos") == 6

    simulator.handle(client, packet("/node", prefix + "/pos"))
    assert OscMessage(simulator.transport.sent[-1][0]).params == ["/%s/pos PRE\n" % prefix]
    simulator.handle(client, packet("/outputs/rec/%02d/src" % number, 12))
    assert state.get("/" + prefix + "/src") == 12


@pytest.mark.parametrize(("address", "value"), [
    ("/outputs/aes/03/src", 1), ("/outputs/aes/01/src", 77),
    ("/outputs/aes/01/pos", 9), ("/outputs/aes/01/invert", 2),
    ("/outputs/rec/03/src", 1), ("/outputs/rec/01/src", 77),
    ("/outputs/rec/01/pos", 9), ("/outputs/rec/01/invert", 1),
])
def test_aes_and_recording_outputs_reject_invalid_values(address, value):
    assert not ConsoleState().update(address, value)


@pytest.mark.parametrize("number", [0, 31, 32, 79, 80, 127])
def test_headamp_node_get_set_and_direct_osc(number):
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    prefix = "headamp/%03d" % number

    simulator.handle(client, packet("/node", prefix))
    assert OscMessage(simulator.transport.sent[-1][0]).params == ["/%s +0.0 OFF\n" % prefix]

    simulator.handle(client, packet("/", prefix + " 24.5 ON"))
    assert state.get("/" + prefix + "/gain") == 24.5
    assert state.get("/" + prefix + "/phantom") == 1

    simulator.handle(client, packet("/node", prefix + "/gain"))
    assert OscMessage(simulator.transport.sent[-1][0]).params == ["/%s/gain +24.5\n" % prefix]
    simulator.handle(client, packet("/", prefix + "/phantom OFF"))
    assert state.get("/" + prefix + "/phantom") == 0

    simulator.handle(client, packet("/headamp/%03d/gain" % number, 18.0))
    assert state.get("/" + prefix + "/gain") == 18.0


@pytest.mark.parametrize(("address", "value"), [
    ("/headamp/128/gain", 0.0), ("/headamp/000/gain", -12.5),
    ("/headamp/000/gain", 60.5), ("/headamp/000/gain", 1.2),
    ("/headamp/000/phantom", 2), ("/headamp/000/unknown", 1),
])
def test_headamp_rejects_invalid_values(address, value):
    assert not ConsoleState().update(address, value)


def test_invalid_headamp_node_write_is_atomic():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    before = dict(simulator.state.headamps[0])
    simulator.handle(client, packet("/", "headamp/000 61 ON"))
    assert simulator.state.headamps[0] == before
    assert simulator.snapshot(outcome="unhandled_set")["events"]



def test_m32_edit_showfile_preferences_and_action_options_accept_node_writes():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    writes = (
        ("/-show/showfile/show/inputs", "ON", 1),
        ("/-show/showfile/show/mxsends", "OFF", 0),
        ("/-show/showfile/show/mxbuses", "ON", 1),
        ("/-show/showfile/show/console", "OFF", 0),
        ("/-show/showfile/show/chan16", "ON", 1),
        ("/-show/showfile/show/chan32", "ON", 1),
        ("/-show/showfile/show/return", "ON", 1),
        ("/-show/showfile/show/buses", "ON", 1),
        ("/-show/showfile/show/lrmtxdca", "ON", 1),
        ("/-show/showfile/show/effects", "ON", 1),
        ("/-prefs/safe_masterlevels", "ON", 1),
        ("/-prefs/show_control", "OFF", 0),
        ("/-prefs/haflags", "ON", 1),
        ("/-prefs/invertmutes", "OFF", 0),
        ("/-action/undopt", "1", 1),
    )
    for address, token, expected in writes:
        simulator.handle(client, packet("/", address.lstrip("/") + " " + token))
        assert state.get(address) == expected
        assert simulator.snapshot(outcome="unhandled_set")["events"] == []

    assert len(simulator.snapshot(outcome="handled_node_set")["events"]) == len(writes)


def test_unknown_root_node_set_reports_actual_header_for_enum_diagnostics():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/", "config/tape/autoplay MAYBE"))

    event = simulator.snapshot(outcome="unhandled_set")["events"][-1]
    assert event["address"] == "/config/tape/autoplay"
    assert "tuple.index(x)" in event["detail"]



@pytest.mark.parametrize("token,expected", [
    ("OFF", 0), ("1s", 1), ("2s", 2), ("3s", 3), ("4s", 4),
    ("5s", 5), ("6s", 6), ("7s", 7), ("8s", 8),
])
def test_rta_peakhold_accepts_console_duration_labels(token, expected):
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/", "-prefs/rta/peakhold " + token))

    assert simulator.state.get("/-prefs/rta/peakhold") == expected
    assert simulator.snapshot(outcome="handled_node_set")["events"]
    simulator.handle(client, packet("/node", "-prefs/rta/peakhold"))
    response = OscMessage(simulator.transport.sent[-1][0])
    assert response.params == ["/-prefs/rta/peakhold " + token + "\n"]


@pytest.mark.parametrize("token,expected", [("REC", 0), ("PLAY", 1)])
def test_config_routing_parent_address_accepts_routing_mode_switch_node_write(token, expected):
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/", "config/routing " + token))

    assert simulator.state.routing.get("/config/routing/outswitch") == expected
    assert "/config/routing/outswitch" in simulator.state.received
    assert simulator.snapshot(outcome="handled_node_set")["events"]
    assert not simulator.snapshot(outcome="unhandled_set")["events"]


@pytest.mark.parametrize("token,expected", [("REC", 0), ("PLAY", 1)])
def test_direct_config_routing_parent_address_accepts_routing_mode_switch(token, expected):
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/config/routing", token))

    assert simulator.state.routing.get("/config/routing/outswitch") == expected
    assert "/config/routing/outswitch" in simulator.state.received
    assert simulator.snapshot(outcome="handled_set")["events"]
    assert not simulator.snapshot(outcome="unhandled_set")["events"]



def test_aes50_routing_accepts_m32_edit_aux_tb_alias():
    from m32_monitor.routing import routing_enum_index, routing_enum_token

    address = "/config/routing/AES50B/41-48"
    assert routing_enum_index(address, "AUX/TB") == 25
    assert routing_enum_index(address, "AUXIN1-6/TB") == 25
    assert routing_enum_token(address, 25) == "AUXIN1-6/TB"


def test_aes50_routing_node_set_accepts_m32_edit_aux_tb_alias():
    simulator = Simulator(ConsoleState())
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)
    values = ["UIN1-8", "UIN9-16", "UIN17-24", "UIN25-32", "P161-8", "AUX/TB"]

    simulator.handle(client, packet("/", "config/routing/AES50B " + " ".join(values)))

    assert simulator.state.routing.get("/config/routing/AES50B/41-48") == 25
    assert simulator.snapshot(outcome="handled_node_set")["events"]
    assert not simulator.snapshot(outcome="unhandled_set")["events"]


def test_eq_gain_accepts_half_tenth_db_values_across_strip_families():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    for address, header in (
        ("/ch/01/eq/2", "ch/01/eq/2"),
        ("/bus/01/eq/2", "bus/01/eq/2"),
        ("/mtx/01/eq/2", "mtx/01/eq/2"),
    ):
        simulator.handle(client, packet("/", header + " PEQ 479.8 -2.25 1.6"))
        assert state.get(address + "/g") == -2.25
        assert not simulator.snapshot(outcome="unhandled_set")["events"]

    assert state.update("/main/st/eq/2/g", -2.25)
    assert state.get("/main/st/eq/2/g") == -2.25


def test_channel_mix_node_set_accepts_negative_infinity_fader_token():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/", "ch/01/mix OFF -oo ON +0 OFF -oo"))

    assert state.get("/ch/01/mix/on") == 0
    assert state.get("/ch/01/mix/fader") == 0.0
    assert state.get("/ch/01/mix/st") == 1
    assert state.get("/ch/01/mix/pan") == 0.0
    assert state.get("/ch/01/mix/mono") == 0
    assert state.get("/ch/01/mix/mlevel") == 0.0
    assert not simulator.snapshot(outcome="unhandled_set")["events"]

def test_channel_bus_send_node_accepts_numeric_pan_follow_enum_and_silent_level():
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/", "ch/01/mix/01 OFF -oo +0 PRE 0"))

    assert state.get("/ch/01/mix/01/on") == 0
    assert state.get("/ch/01/mix/01/level") == 0.0
    assert state.get("/ch/01/mix/01/pan") == 0.0
    assert state.get("/ch/01/mix/01/type") == 3
    assert state.get("/ch/01/mix/01/panFollow") == 0
    assert not simulator.snapshot(outcome="unhandled_set")["events"]

def test_channel_group_node_accepts_percent_binary_dca_and_mute_masks():
    state = ConsoleState()
    simulator = Simulator(state)
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/", "ch/01/grp %01000000 %000000"))

    assert state.get("/ch/01/grp/dca") == 64
    assert state.get("/ch/01/grp/mute") == 0
    assert simulator.snapshot(outcome="unhandled_set")["events"] == []


def test_all_channel_bus_send_nodes_accept_db_levels():
    state = ConsoleState()
    simulator = Simulator(state)
    client = ("127.0.0.1", 50123)

    expected = (5.5 + 30.0) / 40.0
    for channel in range(1, 33):
        for bus in range(1, 17):
            header = "ch/%02d/mix/%02d" % (channel, bus)
            fields = "ON +5.5 +0 PRE 0" if bus % 2 else "ON +5.5"
            simulator.handle(client, packet("/", header + " " + fields))
            assert state.get("/" + header + "/level") == pytest.approx(expected)

    assert simulator.snapshot(outcome="unhandled_set")["events"] == []



def test_auxin_mix_send_level_accepts_db():
    state = ConsoleState()
    simulator = Simulator(state)
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/", "auxin/01/mix/01 ON -18.5 +0 PRE 0"))

    assert state.get("/auxin/01/mix/01/on") == 1
    assert state.get("/auxin/01/mix/01/level") == pytest.approx((-18.5 + 50.0) / 80.0)
    assert state.get("/auxin/01/mix/01/pan") == pytest.approx(0.0)
    assert state.get("/auxin/01/mix/01/type") == 3
    assert simulator.snapshot(outcome="unhandled_set")["events"] == []



def test_channel_mix_node_accepts_fader_level_in_db():
    state = ConsoleState()
    simulator = Simulator(state)
    client = ("127.0.0.1", 50123)

    simulator.handle(client, packet("/", "ch/03/mix OFF -4.3 ON +0 OFF +3.5"))

    assert state.get("/ch/03/mix/on") == 0
    assert state.get("/ch/03/mix/fader") == pytest.approx(((-4.3 + 30.0) / 40.0))
    assert state.get("/ch/03/mix/st") == 1
    assert state.get("/ch/03/mix/pan") == 0.0
    assert state.get("/ch/03/mix/mono") == 0
    assert state.get("/ch/03/mix/mlevel") == pytest.approx((3.5 + 30.0) / 40.0)
    assert simulator.snapshot(outcome="unhandled_set")["events"] == []
