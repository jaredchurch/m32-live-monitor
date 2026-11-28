"""Acceptance checks for simulator surface and captured show-file round trips."""
from pathlib import Path
import math
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
            expected.append(simulator._format_strip_node_value(
                spec, value, field, simulator._strip_node_fader_db(
                    "/" + "/".join(header.split("/")[:2]), node, field)))
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
        actual_tokens = shlex.split(_node_response(simulator, header).strip())
        prefix, node, fields = simulator._strip_node_header(header)
        schema = (state.main_node_schema if prefix == "/main/st" else
                  state.main_mono_node_schema) if prefix in ("/main/st", "/main/m") else state.strip_node_schema[header.split("/")[0]]
        if actual_tokens[0] != "/" + header or len(actual_tokens) != len(fields) + 1:
            mismatches.append((header, "wrong response shape", actual_tokens))
            continue
        for field, source_token, returned_token in zip(fields, expected_values, actual_tokens[1:]):
            fader_db = simulator._strip_node_fader_db(prefix, node, field)
            expected_value = simulator._parse_strip_node_value(
                schema[node][field], source_token, field, fader_db=fader_db)
            returned_value = simulator._parse_strip_node_value(
                schema[node][field], returned_token, field, fader_db=fader_db)
            equal = (math.isclose(expected_value, returned_value, rel_tol=0.0, abs_tol=0.001)
                     if isinstance(expected_value, float) else expected_value == returned_value)
            if not equal:
                mismatches.append((header, field, source_token, returned_token,
                                   expected_value, returned_value))

    assert not mismatches, (
        "Real Jared.scn strip-node values did not round-trip semantically; first mismatches: "
        + repr(mismatches[:20])
    )


def _canonical_state(value):
    """Convert ConsoleState's nested dataclasses and routing objects to comparable data."""
    if hasattr(value, "__dataclass_fields__"):
        return {name: _canonical_state(getattr(value, name))
                for name in value.__dataclass_fields__}
    if isinstance(value, dict):
        return {key: _canonical_state(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_state(item) for item in value]
    if isinstance(value, set):
        return sorted((_canonical_state(item) for item in value), key=repr)
    if hasattr(value, "__dict__"):
        return {key: _canonical_state(item) for key, item in vars(value).items()}
    return value


def _state_differences(expected, actual, path=""):
    if isinstance(expected, dict) and isinstance(actual, dict):
        differences = []
        for key in sorted(set(expected) | set(actual), key=str):
            child = f"{path}.{key}" if path else str(key)
            if key not in expected or key not in actual:
                differences.append((child, expected.get(key, "<missing>"), actual.get(key, "<missing>")))
            else:
                differences.extend(_state_differences(expected[key], actual[key], child))
            if len(differences) >= 40:
                break
        return differences
    if isinstance(expected, list) and isinstance(actual, list):
        differences = []
        if len(expected) != len(actual):
            differences.append((path + ".length", len(expected), len(actual)))
        for index, (left, right) in enumerate(zip(expected, actual)):
            differences.extend(_state_differences(left, right, f"{path}[{index}]"))
            if len(differences) >= 40:
                break
        return differences
    if isinstance(expected, (int, float)) and not isinstance(expected, bool) and isinstance(actual, (int, float)) and not isinstance(actual, bool):
        if math.isclose(float(expected), float(actual), rel_tol=1e-9, abs_tol=1e-6):
            return []
    if expected != actual:
        return [(path, expected, actual)]
    return []


def test_real_jared_scene_round_trips_every_node_through_get_and_set():
    """Import all scene records, export every node, re-import the export and compare all state."""
    source_state = ConsoleState()
    source = Simulator(source_state)
    source.transport = FakeTransport()
    records = [
        line.strip() for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(records) > 2000, f"Jared.scn fixture unexpectedly small: {len(records)} records"

    # Import the complete real scene exactly as M32-Edit's text SET path does.
    for record in records:
        source.handle(CLIENT, packet("/", record))

    import_errors = source.snapshot(outcome="unhandled_set", limit=3000)["events"]
    assert not import_errors, (
        f"Scene import rejected {len(import_errors)} records: "
        + repr([(event["address"], event["detail"]) for event in import_errors[:30]])
    )

    # Export each distinct source node. Some GETs intentionally expand into
    # multiple canonical X32node lines (routing banks, DCA, FX and outputs).
    headers = list(dict.fromkeys(shlex.split(record)[0].lstrip("/") for record in records))
    exported = []
    get_errors = []
    for header in headers:
        before = len(source.transport.sent)
        source.handle(CLIENT, packet("/node", header))
        if len(source.transport.sent) != before + 1:
            get_errors.append((header, "no single /node response"))
            continue
        message = OscMessage(source.transport.sent[-1][0])
        if message.address != "/node" or len(message.params) != 1:
            get_errors.append((header, "invalid response envelope", message.address, message.params))
            continue
        payload = message.params[0]
        if not isinstance(payload, str) or not payload.strip():
            get_errors.append((header, "empty/non-text node response", repr(payload)))
            continue
        exported.extend(line.strip() for line in payload.splitlines() if line.strip())

    assert not get_errors, (
        f"Scene export has {len(get_errors)} unsupported/unreadable nodes: {get_errors[:30]}"
    )
    assert len(exported) > 2000, f"Scene export unexpectedly small: {len(exported)} records"

    # Re-import only what the simulator actually exported. This proves the
    # GET representation is valid input to the same OSC SET interface.
    restored_state = ConsoleState()
    restored = Simulator(restored_state)
    restored.transport = FakeTransport()
    for record in exported:
        restored.handle(CLIENT, packet("/", record))

    export_import_errors = restored.snapshot(outcome="unhandled_set", limit=3000)["events"]
    assert not export_import_errors, (
        f"Exported scene contains {len(export_import_errors)} records the simulator cannot re-import: "
        + repr([(event["address"], event["detail"]) for event in export_import_errors[:30]])
    )

    # Ignore only runtime telemetry. All mixer, routing, FX, DCA, output,
    # headamp, global config and miscellaneous persisted state must match.
    ignored_runtime_fields = {"last_seen", "received", "meters"}
    original = {key: value for key, value in vars(source_state).items()
                if key not in ignored_runtime_fields}
    round_tripped = {key: value for key, value in vars(restored_state).items()
                     if key not in ignored_runtime_fields}
    expected = _canonical_state(original)
    actual = _canonical_state(round_tripped)
    assert actual == expected, (
        "Full Jared.scn state changed during GET/export/SET round trip. "
        "First state differences: " + repr(_state_differences(expected, actual))
    )
