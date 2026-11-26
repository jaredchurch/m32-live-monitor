"""Shared channel-state model used by the simulator and dashboard."""
from dataclasses import asdict, dataclass

@dataclass
class ChannelState:
    number: int
    name: str
    fader: float = 0.75
    muted: bool = False
    colour: int = 0
    source: int = 0
    connected: bool = False
    def as_dict(self):
        return asdict(self)

class ConsoleState:
    def __init__(self):
        self.channels = {n: ChannelState(n, f"CH {n:02d}", 0.72, False, (n-1)%8, n, True) for n in range(1,33)}
        self.online = True
        self.mode = "simulator"

    def update(self, address, value):
        parts = address.strip("/").split("/")
        if len(parts) < 4 or parts[0] != "ch": return False
        try: channel = self.channels[int(parts[1])]
        except (ValueError, KeyError): return False
        path = "/".join(parts[2:])
        if path == "config/name" and isinstance(value, str): channel.name = value
        elif path == "config/color" and isinstance(value, (int,float)): channel.colour = int(value)
        elif path == "config/source" and isinstance(value, (int,float)):
            channel.source = int(value); channel.connected = channel.source > 0
        elif path == "mix/fader" and isinstance(value, (int,float)): channel.fader = max(0.0,min(1.0,float(value)))
        elif path == "mix/on" and isinstance(value, (int,float)): channel.muted = int(value) == 0
        else: return False
        return True

    def get(self, address):
        parts = address.strip("/").split("/")
        if len(parts) < 4 or parts[0] != "ch": return None
        try: channel = self.channels[int(parts[1])]
        except (ValueError, KeyError): return None
        path = "/".join(parts[2:])
        return {"config/name":channel.name,"config/color":channel.colour,"config/source":channel.source,
                "mix/fader":channel.fader,"mix/on":0 if channel.muted else 1}.get(path)

    def visible_channels(self):
        return [c.as_dict() for c in self.channels.values() if c.connected]
