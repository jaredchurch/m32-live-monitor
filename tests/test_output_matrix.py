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
