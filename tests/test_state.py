from m32_monitor.state import ConsoleState

def test_state_exposes_only_connected_channels():
    state=ConsoleState()
    assert len(state.visible_channels())==32
    state.update("/ch/01/config/source",0)
    assert len(state.visible_channels())==31

def test_channel_parameter_updates():
    state=ConsoleState()
    assert state.update("/ch/01/config/name","W1 - Male")
    assert state.update("/ch/01/mix/fader",0.2913)
    assert state.update("/ch/01/mix/on",0)
    channel=state.channels[1]
    assert channel.name=="W1 - Male"
    assert channel.fader==0.2913
    assert channel.muted is True

def test_unknown_parameters_are_ignored():
    assert not ConsoleState().update("/ch/01/unknown/value",1)
