from m32_monitor.state import ConsoleState


def channel_cell(state, channel=1, output="bus_01"):
    return next(row for row in state.output_matrix()["channels"] if row["number"] == channel)["cells"][output]


def test_send_off_and_send_fader_zero_are_distinct():
    state = ConsoleState()
    state.update("/ch/01/mix/01/level", 0.0)
    state.update("/ch/01/mix/01/on", 1)
    cell = channel_cell(state)
    assert cell["muted"] is True
    assert "send_level_zero" in cell["reasons"]
    assert "send_off" not in cell["reasons"]

    state.update("/ch/01/mix/01/level", 0.6)
    state.update("/ch/01/mix/01/on", 0)
    cell = channel_cell(state)
    assert "send_off" in cell["reasons"]
    assert "send_level_zero" not in cell["reasons"]


def test_channel_mute_and_mute_group_are_upstream_of_all_outputs():
    state = ConsoleState()
    state.update("/ch/01/mix/01/level", 0.6)
    state.update("/ch/01/grp/mute", 1)
    state.update("/config/mute/1", 1)

    cell = channel_cell(state)
    assert cell["muted"] is True
    assert "mute_group_1" in cell["reasons"]


def test_dca_mute_obeys_console_dca_mute_preference():
    state = ConsoleState()
    state.update("/ch/01/grp/dca", 1)
    state.update("/dca/1/on", 0)
    state.update("/ch/01/mix/01/level", 0.6)

    cell = channel_cell(state)
    assert cell["uncertain"] is True
    assert "dca_mute_setting_unknown" in cell["reasons"]

    state.update("/-prefs/dcamute", 0)
    assert channel_cell(state)["muted"] is False

    state.update("/-prefs/dcamute", 1)
    cell = channel_cell(state)
    assert cell["muted"] is True
    assert "dca_1_muted" in cell["reasons"]


def test_dca_fader_at_zero_mutes_assigned_channel():
    state = ConsoleState()
    state.update("/ch/01/grp/dca", 1)
    state.update("/dca/1/fader", 0.0)
    state.update("/ch/01/mix/01/level", 0.6)
    cell = channel_cell(state)
    assert "dca_1_fader_zero" in cell["reasons"]


def test_pre_fader_send_is_not_muted_by_channel_fader_zero():
    state = ConsoleState()
    state.update("/ch/01/mix/fader", 0.0)
    state.update("/ch/01/mix/01/type", 3)
    state.update("/ch/01/mix/01/level", 0.6)
    state.update("/ch/01/mix/01/on", 1)
    assert channel_cell(state)["muted"] is False

    state.update("/ch/01/mix/01/type", 4)
    assert "channel_fader_zero" in channel_cell(state)["reasons"]


def test_destination_bus_mute_is_reported_separately():
    state = ConsoleState()
    state.update("/ch/01/mix/01/level", 0.6)
    state.update("/bus/01/mix/on", 0)
    cell = channel_cell(state)
    assert cell["muted"] is True
    assert "output_muted" in cell["reasons"]


def test_main_and_mono_sends_are_separate_destinations():
    state = ConsoleState()
    state.update("/ch/01/mix/fader", 0.6)
    state.update("/ch/01/mix/st", 1)
    state.update("/ch/01/mix/mono", 0)
    cells = next(row for row in state.output_matrix()["channels"] if row["number"] == 1)["cells"]
    assert cells["main_st"]["muted"] is False
    assert "send_off" in cells["main_mono"]["reasons"]


def test_hard_mute_setting_controls_channel_mute_on_pre_fader_sends():
    state = ConsoleState()
    state.update("/ch/01/mix/01/type", 3)
    state.update("/ch/01/mix/01/level", 0.6)
    state.update("/ch/01/mix/01/on", 1)
    state.update("/ch/01/mix/on", 0)

    assert channel_cell(state)["uncertain"] is True
    state.update("/-prefs/hardmute", 0)
    assert channel_cell(state)["muted"] is False
    state.update("/-prefs/hardmute", 1)
    assert "channel_muted" in channel_cell(state)["reasons"]


def test_hardware_matrix_does_not_claim_live_before_route_snapshot_arrives():
    state = ConsoleState()
    state.mode = "hardware"
    state.received.clear()
    state.update("/ch/01/config/source", 1)
    state.update("/ch/01/config/color", 1)

    cell = channel_cell(state)
    assert cell["muted"] is False
    assert cell["uncertain"] is True
    assert "send_switch_state_unknown" in cell["reasons"]


def test_hardware_matrix_marks_path_live_after_required_state_is_received():
    state = ConsoleState()
    state.mode = "hardware"
    state.received.clear()
    for address, value in (
        ("/ch/01/config/source", 1), ("/ch/01/config/color", 1),
        ("/ch/01/mix/on", 1), ("/ch/01/mix/fader", 0.7),
        ("/ch/01/grp/dca", 0), ("/ch/01/grp/mute", 0),
        ("/ch/01/mix/01/type", 4), ("/ch/01/mix/01/on", 1),
        ("/ch/01/mix/01/level", 0.6),
        ("/bus/01/mix/on", 1), ("/bus/01/mix/fader", 0.7),
        ("/bus/01/grp/dca", 0), ("/bus/01/grp/mute", 0),
    ):
        state.update(address, value)

    cell = channel_cell(state)
    assert cell["muted"] is False
    assert cell["uncertain"] is False


def test_destination_dca_and_mute_group_can_mute_bus_output():
    state = ConsoleState()
    state.update("/ch/01/mix/01/level", 0.6)
    state.update("/bus/01/grp/dca", 1)
    state.update("/dca/1/on", 0)
    state.update("/-prefs/dcamute", 1)
    cell = channel_cell(state)
    assert "dca_1_muted" in cell["reasons"]

    state.update("/bus/01/grp/dca", 0)
    state.update("/bus/01/grp/mute", 1)
    state.update("/config/mute/1", 1)
    cell = channel_cell(state)
    assert "output_mute_group_1" in cell["reasons"]


def strip_cell(state, strip_type, number=1, output="bus_01"):
    row = next(row for row in state.output_matrix()["channels"]
               if row["strip_type"] == strip_type and row["number"] == number)
    return row["cells"][output]


def test_aux_input_and_fx_return_appear_as_independent_sources():
    state = ConsoleState()
    state.update("/auxin/01/config/name", "Playback")
    state.update("/auxin/01/config/source", 33)
    state.update("/auxin/01/config/color", 2)
    state.update("/auxin/01/mix/01/level", 0.6)
    state.update("/auxin/01/mix/01/on", 1)
    state.update("/fxrtn/01/config/name", "Hall Return")
    state.update("/fxrtn/01/config/color", 3)
    state.update("/fxrtn/01/mix/01/level", 0.6)
    state.update("/fxrtn/01/mix/01/on", 1)

    assert strip_cell(state, "aux")["muted"] is False
    assert strip_cell(state, "fx_return")["muted"] is False
    visible = state.visible_channels()
    assert any(item["stripType"] == "aux" for item in visible)
    assert any(item["stripType"] == "fx_return" for item in visible)


def test_aux_and_fx_return_mute_and_dca_are_applied_to_sends():
    state = ConsoleState()
    state.update("/auxin/01/config/source", 33)
    state.update("/auxin/01/config/color", 1)
    state.update("/fxrtn/01/config/color", 1)
    state.update("/auxin/01/mix/01/level", 0.6)
    state.update("/auxin/01/mix/01/on", 1)
    state.update("/auxin/01/mix/on", 0)
    assert "channel_muted" in strip_cell(state, "aux")["reasons"]

    state.update("/fxrtn/01/mix/01/level", 0.6)
    state.update("/fxrtn/01/mix/01/on", 1)
    state.update("/fxrtn/01/grp/dca", 1)
    state.update("/dca/1/fader", 0.0)
    assert "dca_1_fader_zero" in strip_cell(state, "fx_return")["reasons"]


def test_bus_and_main_matrix_sends_have_distinct_switch_and_zero_states():
    state = ConsoleState()
    state.update("/bus/01/mix/01/on", 1)
    state.update("/bus/01/mix/01/level", 0.0)
    cell = state.matrix_input_matrix()["sources"][0]["cells"]["mtx_01"]
    assert "send_level_zero" in cell["reasons"]

    state.update("/bus/01/mix/01/level", 0.6)
    state.update("/bus/01/mix/01/on", 0)
    cell = state.matrix_input_matrix()["sources"][0]["cells"]["mtx_01"]
    assert "send_off" in cell["reasons"]

    state.update("/main/st/mix/01/on", 1)
    state.update("/main/st/mix/01/level", 0.6)
    row = next(r for r in state.matrix_input_matrix()["sources"] if r["id"] == "main_st")
    assert row["cells"]["mtx_01"]["muted"] is False


def test_matrix_output_mute_fader_dca_and_mute_group_are_applied():
    state = ConsoleState()
    state.update("/bus/01/mix/01/on", 1)
    state.update("/bus/01/mix/01/level", 0.6)
    state.update("/mtx/01/mix/on", 0)
    cell = state.matrix_input_matrix()["sources"][0]["cells"]["mtx_01"]
    assert "output_muted" in cell["reasons"]

    state.update("/mtx/01/mix/on", 1)
    state.update("/mtx/01/mix/fader", 0.0)
    cell = state.matrix_input_matrix()["sources"][0]["cells"]["mtx_01"]
    assert "output_fader_zero" in cell["reasons"]

    state.update("/mtx/01/mix/fader", 0.6)
    state.update("/mtx/01/grp/dca", 1)
    state.update("/dca/1/fader", 0.0)
    cell = state.matrix_input_matrix()["sources"][0]["cells"]["mtx_01"]
    assert "dca_1_fader_zero" in cell["reasons"]


def test_matrix_path_requires_hardware_snapshot_before_showing_open():
    state = ConsoleState()
    state.mode = "hardware"
    state.received.clear()
    cell = state.matrix_input_matrix()["sources"][0]["cells"]["mtx_01"]
    assert cell["uncertain"] is True
    assert "matrix_send_switch_unknown" in cell["reasons"]

    for address, value in (
        ("/bus/01/mix/on", 1), ("/bus/01/mix/fader", 0.7),
        ("/bus/01/grp/dca", 0), ("/bus/01/grp/mute", 0),
        ("/bus/01/mix/01/on", 1), ("/bus/01/mix/01/level", 0.6),
        ("/mtx/01/mix/on", 1), ("/mtx/01/mix/fader", 0.7),
        ("/mtx/01/grp/dca", 0), ("/mtx/01/grp/mute", 0),
    ):
        state.update(address, value)
    cell = state.matrix_input_matrix()["sources"][0]["cells"]["mtx_01"]
    assert cell["muted"] is False
    assert cell["uncertain"] is False


def test_simulator_get_supports_matrix_and_matrix_send_parameters():
    state = ConsoleState()
    state.update("/bus/01/mix/02/on", 0)
    state.update("/bus/01/mix/02/level", 0.4)
    state.update("/mtx/02/mix/on", 0)
    assert state.get("/bus/01/mix/02/on") == 0
    assert state.get("/bus/01/mix/02/level") == 0.4
    assert state.get("/mtx/02/mix/on") == 0


def test_mono_c_send_level_at_zero_is_distinguished():
    state = ConsoleState()
    state.update("/ch/01/mix/mono", 1)
    state.update("/ch/01/mix/mlevel", 0.0)
    cell = next(row for row in state.output_matrix()["channels"] if row["number"] == 1)["cells"]["main_mono"]
    assert "send_level_zero" in cell["reasons"]
