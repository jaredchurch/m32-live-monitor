"""Repeatable console presets for exercising the browser monitor and OSC clients."""
SCENARIOS = {
    "service": {"name": "Sunday service", "description": "Vocals, instruments, playback and FX returns."},
    "full-band": {"name": "Full band", "description": "24 connected inputs, Aux inputs and FX returns."},
    "mute-test": {"name": "Mute and DCA test", "description": "Channel mutes, mute groups and DCA states."},
    "patching-test": {"name": "Patching and visibility test", "description": "Connected, unpatched and scribble-strip-disabled channels."},
}


def list_scenarios():
    return [{"id": key, **value} for key, value in SCENARIOS.items()]


def apply_scenario(state, scenario_id):
    if scenario_id not in SCENARIOS:
        raise ValueError("Unknown simulator scenario: %s" % scenario_id)
    for channel in state.channels.values():
        channel.name = "CH %02d" % channel.number
        channel.fader, channel.muted = 0.72, False
        channel.colour, channel.source, channel.connected = ((channel.number - 1) % 15) + 1, 0, False
        channel.dca_mask = channel.mute_mask = 0
        channel.main_st, channel.main_mono, channel.main_mono_level = True, False, 1.0
        channel.sends.clear()
        channel.send_types.clear()
    for collection in (state.auxins, state.fx_returns):
        for channel in collection.values():
            channel.connected, channel.source = False, 0
            if collection is state.fx_returns:
                channel.colour = 0
    for number, dca in state.dcas.items():
        dca.update(name="DCA %d" % number, on=True, fader=0.75)
    state.mute_groups = {number: False for number in range(1, 7)}
    state.dca_mutes_enabled = state.hard_mutes_enabled = True

    if scenario_id == "service":
        specs = [(1,"W1 - Lead Vocal",1,1),(2,"W2 - Vocal",2,1),(3,"W3 - Vocal",3,1),
          (4,"W4 - Vocal",4,1),(5,"Acoustic Gtr",5,3),(6,"Electric Gtr",6,3),
          (7,"Bass DI",7,4),(8,"Keys L",8,5),(9,"Keys R",9,5),(10,"Drum Kick",10,2),
          (11,"Drum Snare",11,2),(12,"Playback L",12,6),(13,"Playback R",13,6)]
    elif scenario_id == "full-band":
        names = ["Lead Vocal","Backing Vox 1","Backing Vox 2","Backing Vox 3","Acoustic",
          "Electric 1","Electric 2","Bass DI","Keys L","Keys R","Piano L","Piano R",
          "Kick In","Kick Out","Snare Top","Snare Bottom","Tom 1","Tom 2","Floor Tom",
          "Overhead L","Overhead R","Playback L","Playback R","Click"]
        specs = [(n,name,n, 1 if n <= 4 else 3 if n <= 7 else 4 if n == 8 else 5 if n <= 12 else 2 if n <= 21 else 6)
                 for n,name in enumerate(names,1)]
    elif scenario_id == "mute-test":
        specs = [(1,"Lead Vocal",1,1),(2,"Backing Vox",2,1),(3,"Guitar",3,3),(4,"Bass",4,4),
                 (5,"Keys",5,5),(6,"Kick",6,2),(7,"Snare",7,2),(8,"Playback",8,6)]
    else:
        specs = [(1,"Connected Vocal",1,1),(2,"Connected Guitar",2,3),(3,"No Input Source",0,3),
                 (4,"Strip Disabled",4,0),(5,"Connected Bass",5,4),(6,"Unpatched Keys",0,5),
                 (7,"Playback",7,6)]

    for number,name,source,colour in specs:
        channel=state.channels[number]
        channel.name,channel.source,channel.colour=name,source,colour
        channel.connected=source>0
        channel.fader=0.68+(number%4)*0.07
        channel.sends={1:{"on":True,"level":0.65},2:{"on":True,"level":0.55}}
        channel.send_types={1:4,2:4}
        channel.dca_mask=1 if number<=4 else 2 if number<=8 else 0
        channel.mute_mask=1 if number in (2,3) else 0

    for number,name,source in ((1,"Wireless IEM",33),(2,"Playback Aux",34)):
        aux=state.auxins[number]
        aux.name,aux.source,aux.connected,aux.colour,aux.fader=name,source,True,3,0.7
    for number,name in ((1,"Hall Reverb L"),(2,"Hall Reverb R"),(3,"Plate L"),(4,"Plate R")):
        fx=state.fx_returns[number]
        fx.name,fx.colour,fx.connected,fx.source,fx.fader=name,5,True,40+number,0.65
    state.dcas[1].update(name="Vocals",on=True,fader=0.78)
    state.dcas[2].update(name="Band",on=True,fader=0.82)

    if scenario_id == "mute-test":
        state.channels[2].muted=True
        state.channels[6].muted=True
        state.channels[3].mute_mask=1
        state.channels[4].dca_mask=2
        state.dcas[2]["on"]=False
        state.mute_groups[1]=True
        state.channels[5].fader=0.0
    elif scenario_id == "patching-test":
        state.channels[4].colour=0
        state.channels[6].source=0
        state.channels[6].connected=False
    state.received.clear()
    state.mode="simulator"
    return {"id":scenario_id,**SCENARIOS[scenario_id]}
