from m32_monitor.state import ConsoleState

def test_channels_without_source_or_scribble_colour_are_hidden():
    state=ConsoleState()
    assert len(state.visible_channels())==32
    state.update("/ch/01/config/source",0)
    state.update("/ch/02/config/color",0)
    visible=[c["number"] for c in state.visible_channels()]
    assert 1 not in visible and 2 not in visible
    assert len(visible)==30

def test_channel_parameter_updates():
    state=ConsoleState()
    assert state.update("/ch/01/config/name","W1 - Male")
    assert state.update("/ch/01/mix/fader",0.2913)
    assert state.update("/ch/01/mix/on",0)
    channel=state.channels[1]
    assert channel.name=="W1 - Male"
    assert channel.fader==0.2913
    assert channel.muted is True

def test_source_label_decoding():
    assert ConsoleState.source_label(1)=="IN01"
    assert ConsoleState.source_label(33)=="AUX1"
    assert ConsoleState.source_label(41)=="FX1L"
    assert ConsoleState.source_label(49)=="BUS01"

def test_hardware_connection_times_out():
    state=ConsoleState()
    state.mode="hardware"
    state.last_seen=None
    assert state.online is False
    state.mark_seen()
    assert state.online is True
    state.last_seen=0
    assert state.online is False


def test_stereo_linked_channels_render_as_one_monitor_strip():
    state = ConsoleState()
    assert state.update("/config/chlink/1-2", 1)
    visible = state.visible_channels()
    pair = next(channel for channel in visible if channel["number"] == 1)
    assert pair["stereoLinked"] is True
    assert pair["linkedNumber"] == 2
    assert pair["linkedName"] == state.channels[2].name
    assert 2 not in [channel["number"] for channel in visible]
    assert len(visible) == 31


def test_stereo_link_values_must_be_binary():
    state = ConsoleState()
    assert state.update("/config/chlink/1-2", 1) is True
    assert state.update("/config/chlink/3-4", 2) is False
    assert state.update("/config/chlink/5-6", "ON") is False


def test_channel_layout_includes_off_slots_and_stereo_pair_metadata():
    state = ConsoleState()
    state.update("/ch/01/config/source", 0)
    state.update("/config/chlink/3-4", 1)
    strips = state.visible_channels(include_off=True)
    channel_strips = [item for item in strips if item["stripType"] == "channel"]
    assert len(channel_strips) == 31
    assert channel_strips[0]["active"] is False
    pair = next(item for item in channel_strips if item["number"] == 3)
    assert pair["stereoLinked"] is True
    assert pair["linkedNumber"] == 4
    assert pair["linkedDcaMask"] == state.channels[4].dca_mask
