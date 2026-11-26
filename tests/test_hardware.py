import pytest

from pythonosc.osc_bundle_builder import IMMEDIATELY, OscBundleBuilder
from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import OscMessageBuilder

from m32_monitor.hardware import HardwareMonitor
from m32_monitor.state import ConsoleState


def message(address, *args):
    builder = OscMessageBuilder(address=address)
    for arg in args:
        builder.add_arg(arg)
    return builder.build()


def test_hardware_monitor_applies_individual_osc_updates():
    state = ConsoleState()
    monitor = HardwareMonitor(state, "192.0.2.10", 10023, "127.0.0.1", 10024)

    builder = OscMessageBuilder(address="/ch/01/config/name")
    builder.add_arg("W1 - Male")
    monitor._process_datagram(builder.build().dgram)

    assert state.channels[1].name == "W1 - Male"
    assert state.last_seen is not None


def test_hardware_monitor_applies_messages_inside_osc_bundle():
    state = ConsoleState()
    monitor = HardwareMonitor(state, "192.0.2.10", 10023, "127.0.0.1", 10024)
    bundle = OscBundleBuilder(IMMEDIATELY)
    for address, value in (
        ("/ch/01/config/name", "W1 - Male"),
        ("/ch/01/config/color", 2),
        ("/ch/01/config/source", 7),
        ("/ch/01/mix/fader", 0.2913),
        ("/ch/01/mix/on", 0),
    ):
        bundle.add_content(message(address, value))

    monitor._process_datagram(bundle.build().dgram)

    channel = state.channels[1]
    assert channel.name == "W1 - Male"
    assert channel.colour == 2
    assert channel.source == 7
    assert channel.connected is True
    assert channel.fader == pytest.approx(0.2913)
    assert channel.muted is True
    assert state.visible_channels()[0]["number"] == 1


def test_hardware_monitor_does_not_mark_unknown_messages_as_console_activity():
    state = ConsoleState()
    state.mode = "hardware"
    state.last_seen = None
    monitor = HardwareMonitor(state, "192.0.2.10", 10023, "127.0.0.1", 10024)
    builder = OscMessageBuilder(address="/unrecognised/path")
    builder.add_arg(1)

    monitor._process_datagram(builder.build().dgram)

    assert state.last_seen is None


def test_hardware_monitor_ignores_malformed_osc_datagram():
    state = ConsoleState()
    monitor = HardwareMonitor(state, "192.0.2.10", 10023, "127.0.0.1", 10024)

    monitor._process_datagram(b"not an OSC packet")

    assert state.channels[1].name == "CH 01"


def test_hardware_monitor_send_builds_enquiry_without_arguments():
    class FakeSocket:
        def __init__(self):
            self.sent = []

        def sendto(self, data, destination):
            self.sent.append((data, destination))

    monitor = HardwareMonitor(ConsoleState(), "192.0.2.10", 10023, "127.0.0.1", 10024)
    monitor.sock = FakeSocket()
    monitor._send("/xremote")

    data, destination = monitor.sock.sent[0]
    sent = OscMessage(data)
    assert destination == ("192.0.2.10", 10023)
    assert sent.address == "/xremote"
    assert sent.params == []

def test_hardware_monitor_records_unexpected_address():
    state = ConsoleState()
    monitor = HardwareMonitor(state, "192.0.2.10", 10023, "127.0.0.1", 10024)
    monitor._process_datagram(message("/vendor/private/parameter", 12).dgram)
    assert monitor.diagnostics.counters["unexpected_addresses"] == 1


def test_hardware_monitor_records_wrong_argument_type_for_expected_address():
    state = ConsoleState()
    monitor = HardwareMonitor(state, "192.0.2.10", 10023, "127.0.0.1", 10024)
    monitor.diagnostics.begin_cycle(["/ch/01/mix/fader"])
    monitor._process_datagram(message("/ch/01/mix/fader", "not-a-number").dgram)
    assert monitor.diagnostics.counters["invalid_responses"] == 1
    assert "/ch/01/mix/fader" not in state.received


def test_hardware_monitor_records_malformed_packet():
    state = ConsoleState()
    monitor = HardwareMonitor(state, "192.0.2.10", 10023, "127.0.0.1", 10024)
    monitor._process_datagram(b"not an OSC packet")
    assert monitor.diagnostics.counters["malformed_packets"] == 1


def test_hardware_monitor_rejects_unexpected_peer():
    state = ConsoleState()
    monitor = HardwareMonitor(state, "192.0.2.10", 10023, "127.0.0.1", 10024)
    monitor._process_datagram(message("/info").dgram, ("198.51.100.7", 10023))
    assert monitor.diagnostics.counters["unexpected_peers"] == 1
    assert state.last_seen is not None or state.mode == "simulator"
