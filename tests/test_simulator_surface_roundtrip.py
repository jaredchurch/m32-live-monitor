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
FIXTURE = Path(__file__).parent / "fixtures" / "real_m32_showfile_nodes.txt"


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
        expected = [
            simulator._format_strip_node_value(schema[node][field], schema[node][field][0])
            for field in fields
        ]
        assert tokens[1:] == expected, (
            f"Default values differ for {header}: expected {expected}, got {tokens[1:]}"
        )

    assert not simulator.snapshot(outcome="unhandled_command")["events"]
    assert not simulator.snapshot(outcome="unhandled_get")["events"]


@pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="Supply a real M32-Edit show-file node capture as the fixture",
)
def test_real_m32_showfile_fixture_round_trips_through_simulator():
    """Load captured show-file SET records and GET each imported node."""
    state = ConsoleState()
    simulator = Simulator(state)
    simulator.transport = FakeTransport()
    records = [
        line.strip() for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert records, "Real show-file fixture is empty"

    imported = {}
    for record in records:
        header, _, _ = record.partition(" ")
        assert header.startswith("/-showfile/"), (
            f"Fixture must contain captured show-file node records, got {record!r}"
        )
        simulator.handle(CLIENT, packet("/", record.lstrip("/")))
        assert state.get(header) is not None, f"Simulator did not retain {header}"
        imported[header] = record

    for address, expected in imported.items():
        actual = _node_response(simulator, address.lstrip("/"))
        assert actual.rstrip("\\n") == expected, (
            f"Show-file round-trip mismatch for {address}: expected {expected!r}, got {actual!r}"
        )

    assert not simulator.snapshot(outcome="unhandled_set")["events"]
    assert not simulator.snapshot(outcome="unhandled_command")["events"]
