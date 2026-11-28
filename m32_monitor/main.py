"""FastAPI application and runtime lifecycle."""
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from m32_monitor.config import get_settings
from m32_monitor.hardware import HardwareMonitor
from m32_monitor.simulator import Simulator
from m32_monitor.state import ConsoleState
from m32_monitor.scenarios import apply_scenario, list_scenarios
from m32_monitor.osc_catalogue import catalogue_snapshot

settings=get_settings()
state=ConsoleState()
runtime=None

@asynccontextmanager
async def lifespan(_app):
    global runtime
    if settings.mode=="simulator":
        state.mode="simulator"
        runtime=Simulator(state, settings.simulator_host, settings.simulator_port,
                          name=settings.simulator_name, model=settings.simulator_model,
                          firmware=settings.simulator_firmware,
                          server_version=settings.simulator_server_version)
        apply_scenario(state, "service")
    else:
        runtime=HardwareMonitor(state,settings.m32_host,settings.m32_port,
                                settings.osc_listen_host,settings.osc_listen_port)
    await runtime.start()
    try: yield
    finally:
        await runtime.stop()
        runtime=None

app=FastAPI(title="M32 Simulation",version="0.2.0",
            description="Local-first, read-only monitoring for a Midas M32.",lifespan=lifespan)

@app.get("/")
def home():
    return FileResponse(Path(__file__).parent/"web"/"index.html")

@app.get("/health")
def health():
    return {"status":"ok"}

@app.get("/api/status")
def status():
    online=state.online
    return {"application":"M32 Simulation","mode":state.mode,
            "m32_host":settings.m32_host if settings.mode=="hardware" else None,
            "m32_port":settings.m32_port,"osc_listen_port":settings.osc_listen_port,
            "connection":"connected" if online else "waiting for console",
            "online":online,"read_only":settings.mode=="hardware"}

@app.get("/api/channels")
def channels():
    """Return input strips and bus masters with DCA assignments and EQ settings."""
    result=[]
    for channel in state.visible_channels(include_off=True):
        kind = channel.get("stripType")
        family = {"channel": "ch", "aux": "auxin", "fx_return": "fxrtn"}[kind]
        prefix = "/%s/%02d/" % (family, channel["number"])
        channel["sourceLabel"] = ("FX RETURN" if kind == "fx_return"
                                  else state.source_label(channel["source"]))
        masks = [channel.get("dca_mask", 0)]
        if channel.get("stereoLinked"):
            masks.append(channel.get("linkedDcaMask", 0))
        assigned = sorted({n for mask in masks for n in range(1, 9) if mask & (1 << (n - 1))})
        channel["dcaNumbers"] = assigned
        channel["dcaLabels"] = [{"number": n, "name": state.dcas[n]["name"],
                                  "muted": state.dca_mutes_enabled is True and not state.dcas[n]["on"],
                                  "fader": state.dcas[n]["fader"]} for n in assigned]
        channel["mutedDcas"] = [n for n in assigned
                                if state.dca_mutes_enabled is True and not state.dcas[n]["on"]]
        channel["dcaMuteUnknown"] = [n for n in assigned if state.dca_mutes_enabled is None]
        channel["eqOn"] = bool(state.strip_nodes.get(prefix + "eq/on", 0))
        band_count = 6 if family == "bus" else 4
        channel["eqBands"] = [
            {"number": band, "type": state.strip_nodes.get(prefix + "eq/%d/type" % band, 2),
             "frequency": state.strip_nodes.get(prefix + "eq/%d/f" % band, 1000.0),
             "gain": state.strip_nodes.get(prefix + "eq/%d/g" % band, 0.0),
             "q": state.strip_nodes.get(prefix + "eq/%d/q" % band, 1.0)}
            for band in range(1, band_count + 1)]
        result.append(channel)

    for number, bus in state.buses.items():
        prefix = "/bus/%02d/" % number
        assigned = [n for n in range(1, 9) if bus["dca_mask"] & (1 << (n - 1))]
        result.append({
            **bus, "stripType": "bus", "active": bool(bus["colour"] != 0),
            "offReason": "STRIP OFF" if bus["colour"] == 0 else "",
            "sourceLabel": "BUS MASTER", "muted": not bus["on"],
            "dcaNumbers": assigned,
            "dcaLabels": [{"number": n, "name": state.dcas[n]["name"],
                           "muted": state.dca_mutes_enabled is True and not state.dcas[n]["on"],
                           "fader": state.dcas[n]["fader"]} for n in assigned],
            "mutedDcas": [n for n in assigned
                          if state.dca_mutes_enabled is True and not state.dcas[n]["on"]],
            "dcaMuteUnknown": [n for n in assigned if state.dca_mutes_enabled is None],
            "eqOn": bool(state.strip_nodes.get(prefix + "eq/on", 0)),
            "eqBands": [{"number": band,
                         "type": state.strip_nodes.get(prefix + "eq/%d/type" % band, 2),
                         "frequency": state.strip_nodes.get(prefix + "eq/%d/f" % band, 1000.0),
                         "gain": state.strip_nodes.get(prefix + "eq/%d/g" % band, 0.0),
                         "q": state.strip_nodes.get(prefix + "eq/%d/q" % band, 1.0)}
                        for band in range(1, 7)]
        })
    return result


@app.get("/api/strip/{family}/{number}")
def strip_detail(family: str, number: int):
    """Return the complete known parameter snapshot for one console strip."""
    collections = {"ch": state.channels, "auxin": state.auxins,
                   "fxrtn": state.fx_returns, "bus": state.buses}
    if family not in collections or number not in collections[family]:
        raise HTTPException(status_code=404, detail="Unknown strip")
    schema = state.strip_node_schema[family]
    prefix = "/%s/%02d/" % (family, number)
    groups = []
    for node, fields in schema.items():
        values = []
        for field_name, spec in fields.items():
            address = prefix + node + "/" + field_name
            value = state.strip_nodes.get(address)
            enum = spec[5]
            display = (enum[int(value)] if enum and isinstance(value, (int, float))
                       and int(value) == value and 0 <= int(value) < len(enum)
                       else value)
            values.append({"name": field_name, "value": value, "display": display,
                           "enum": list(enum) if enum else None,
                           "known": address in state.received or settings.mode == "simulator"})
        groups.append({"name": node, "values": values})
    strip = collections[family][number]
    if hasattr(strip, "as_dict"):
        strip = strip.as_dict()
    return {"family": family, "number": number, "strip": strip,
            "groups": groups, "mode": settings.mode}


@app.get("/api/output-matrix")
def output_matrix():
    """Effective per-channel signal paths, including the reason for each mute."""
    return state.output_matrix()


@app.get("/api/matrix-inputs")
def matrix_inputs():
    """Effective Bus/Main-to-Matrix signal paths."""
    return state.matrix_input_matrix()


@app.get("/api/routing-map")
def routing_map():
    """Return patchbay, FX and monitor routing assignments with freshness markers."""
    return state.routing.snapshot()


@app.get("/api/diagnostics")
def diagnostics():
    """Structured OSC transport and protocol diagnostics."""
    if settings.mode != "hardware" or runtime is None:
        return {"mode": settings.mode, "available": False, "message": "OSC diagnostics are available in hardware mode."}
    return {"mode": settings.mode, "available": True, **runtime.diagnostics.snapshot(state.online)}


@app.get("/api/meters")
def meters():
    """Latest read-only audio meter streams received from the console."""
    return state.meters_snapshot()


@app.get("/api/osc-catalogue")
def osc_catalogue():
    """Categorized X32/M32 OSC address-family and command catalogue."""
    return catalogue_snapshot()


@app.get("/api/simulator/scenarios")
def simulator_scenarios():
    """Available deterministic simulator presets."""
    if settings.mode != "simulator":
        raise HTTPException(status_code=409, detail="Scenarios are only available in simulator mode")
    return {"scenarios": list_scenarios()}


@app.post("/api/simulator/scenarios/{scenario_id}")
def select_simulator_scenario(scenario_id: str):
    """Reset simulator state to a named scenario."""
    if settings.mode != "simulator":
        raise HTTPException(status_code=409, detail="Scenarios are only available in simulator mode")
    try:
        selected = apply_scenario(state, scenario_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if runtime is not None:
        runtime.record("system", "scenario_loaded", detail=selected)
    return selected


@app.get("/api/simulator/logs")
def simulator_logs(limit: int = 500, direction: str | None = None,
                   outcome: str | None = None, search: str | None = None,
                   exceptions_only: bool = False, all_events: bool = False):
    """Recent inbound/outbound OSC traffic, including unsupported requests."""
    if settings.mode != "simulator" or runtime is None:
        raise HTTPException(status_code=409, detail="Simulator logs are only available in simulator mode")
    return runtime.snapshot(limit=None if all_events else limit, direction=direction, outcome=outcome, search=search,
                            exceptions_only=exceptions_only)


@app.post("/api/simulator/logs/pause")
def pause_simulator_logs(paused: bool = True):
    """Pause or resume capture of simulator OSC events."""
    if settings.mode != "simulator" or runtime is None:
        raise HTTPException(status_code=409, detail="Simulator logs are only available in simulator mode")
    return {"logging_paused": runtime.set_logging_paused(paused)}


@app.delete("/api/simulator/logs")
def clear_simulator_logs():
    """Clear the in-memory simulator OSC event log."""
    if settings.mode != "simulator" or runtime is None:
        raise HTTPException(status_code=409, detail="Simulator logs are only available in simulator mode")
    runtime.clear_events()
    return {"cleared": True}
