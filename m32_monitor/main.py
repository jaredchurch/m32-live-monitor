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

app=FastAPI(title="M32 Live Monitor",version="0.2.0",
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
    return {"application":"M32 Live Monitor","mode":state.mode,
            "m32_host":settings.m32_host if settings.mode=="hardware" else None,
            "m32_port":settings.m32_port,"osc_listen_port":settings.osc_listen_port,
            "connection":"connected" if online else "waiting for console",
            "online":online,"read_only":settings.mode=="hardware"}

@app.get("/api/channels")
def channels():
    result=[]
    for channel in state.visible_channels():
        channel["sourceLabel"] = ("FX RETURN" if channel.get("stripType") == "fx_return"
                                else state.source_label(channel["source"]))
        result.append(channel)
    return result


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
                   outcome: str | None = None, search: str | None = None):
    """Recent inbound/outbound OSC traffic, including unsupported requests."""
    if settings.mode != "simulator" or runtime is None:
        raise HTTPException(status_code=409, detail="Simulator logs are only available in simulator mode")
    return runtime.snapshot(limit=limit, direction=direction, outcome=outcome, search=search)


@app.delete("/api/simulator/logs")
def clear_simulator_logs():
    """Clear the in-memory simulator OSC event log."""
    if settings.mode != "simulator" or runtime is None:
        raise HTTPException(status_code=409, detail="Simulator logs are only available in simulator mode")
    runtime.clear_events()
    return {"cleared": True}
