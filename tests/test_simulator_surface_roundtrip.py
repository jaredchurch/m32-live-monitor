"""Acceptance checks for simulator surface and captured show-file round trips."""
from pathlib import Path
import shlex

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


CLIENT = ("127.0.0.1", 50123)
FIXTURE = Path(__file__).parent / "fixtures" / "Jared.scn"


def _node_response(simulator, header):
    before = len(simulator.transport.sent)
    simulator.handle(CLIENT, packet("/node", header))
    assert len(simulator.transport.sent) == before + 1, f"No response for /node {header}"
    message = OscMessage(simulator.transport.sent[-1][0])
    assert message.address == "/node"
    assert len(message.params) == 1
    return message.params[0]


def test_default_surface_all_processing_nodes_match_declared_defaults():
    """Extract every declared strip/main node and compare with its schema defaults."""
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    requests = []

    for family, schema in state.strip_node_schema.items():
        limit = {"ch": 32, "auxin": 8, "fxrtn": 8, "bus": 16, "mtx": 6}[family]
        for number in range(1, limit + 1):
            prefix = f"{family}/{number:02d}"
            requests.extend((f"{prefix}/{node}", fields) for node, fields in schema.items())

    for prefix, schema in (("main/st", state.main_node_schema),
                           ("main/m", state.main_mono_node_schema)):
        requests.extend((f"{prefix}/{node}", fields) for node, fields in schema.items())

    assert requests
    for header, fields in requests:
        response = _node_response(simulator, header)
        tokens = shlex.split(response.strip())
        assert tokens[0] == "/" + header, f"Wrong node returned for {header}: {response!r}"
        assert len(tokens) == len(fields) + 1, (
            f"Incomplete default node {header}: expected {len(fields)} values, got {tokens[1:]}"
        )
        schema = (state.main_node_schema if header.startswith("main/st/")
                  else state.main_mono_node_schema if header.startswith("main/m/")
                  else state.strip_node_schema[header.split("/")[0]])
        node = "/".join(header.split("/")[2:])
        expected = []
        for field in fields:
            spec = schema[node][field]
            value = state.get("/" + header + "/" + field)
            if value is None:
                value = spec[0]
            expected.append(simulator._format_strip_node_value(spec, value))
        expected_tokens = shlex.split(" ".join(expected))
        assert tokens[1:] == expected_tokens, (
            f"Default values differ for {header}: expected {expected_tokens}, got {tokens[1:]}"
        )

    assert not simulator.snapshot(outcome="unhandled_command")["events"]
    assert not simulator.snapshot(outcome="unhandled_get")["events"]


def test_real_jared_scene_imports_and_supported_nodes_read_back():
    """Import the real Jared.scn through the OSC text-write path and compare node values."""
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    records = [
        line.strip() for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(records) > 1000, f"Jared.scn fixture unexpectedly small: {len(records)} records"

    # M32-Edit sends each scene record as the sole string argument to OSC '/'.
    for record in records:
        simulator.handle(CLIENT, packet("/", record))

    supported = []
    for record in records:
        source_tokens = shlex.split(record)
        header = source_tokens[0].lstrip("/")
        if simulator._strip_node_header(header) is not None:
            supported.append((header, source_tokens[1:]))

    assert len(supported) > 500, (
        f"Expected broad strip-node coverage from real scene, found {len(supported)}"
    )
    mismatches = []
    for header, expected_values in supported:
        actual = shlex.split(_node_response(simulator, header).strip())
        expected = ["/" + header, *expected_values]
        if actual != expected:
            mismatches.append((header, expected, actual))

    assert not mismatches, (
        "Real Jared.scn strip-node values did not round-trip; first mismatches: "
        + repr(mismatches[:20])
    )
    assert not simulator.snapshot(outcome="unhandled_set")["events"], (
        "Scene import produced unhandled SET records"
    )
