from m32_monitor.state import ConsoleState

def test_channels_without_source_or_scribble_colour_are_hidden():
    state=ConsoleState()
    assert len(state.visible_channels())==32
    state.update("/ch/01/config/source",0)
    state.update("/ch/02/config/color",0)
    visible=[c["number"] for c in state.visible_channels()]
    assert 1 not in visible
    assert 2 not in visible
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
