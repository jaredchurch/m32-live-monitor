"""Runtime configuration for local, container and simulator modes."""
from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    mode: str
    m32_host: str
    m32_port: int
    osc_listen_host: str
    osc_listen_port: int
    simulator_host: str
    simulator_port: int

def get_settings():
    mode=os.getenv("M32_MODE","simulator").lower()
    if mode not in {"simulator","hardware"}:
        raise ValueError("M32_MODE must be 'simulator' or 'hardware'")
    return Settings(mode,os.getenv("M32_HOST","192.168.1.100"),
        int(os.getenv("M32_PORT","10023")),os.getenv("OSC_LISTEN_HOST","0.0.0.0"),
        int(os.getenv("OSC_LISTEN_PORT","10024")),os.getenv("SIMULATOR_HOST","0.0.0.0"),
        int(os.getenv("SIMULATOR_PORT","10023")))
