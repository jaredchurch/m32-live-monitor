"""FastAPI application and runtime lifecycle."""
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from m32_monitor.config import get_settings
from m32_monitor.hardware import HardwareMonitor
from m32_monitor.simulator import Simulator
from m32_monitor.state import ConsoleState

settings=get_settings()
state=ConsoleState()
runtime=None

@asynccontextmanager
async def lifespan(_app):
    global runtime
    if settings.mode=="simulator":
        state.mode="simulator"
        runtime=Simulator(state,settings.simulator_host,settings.simulator_port)
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
