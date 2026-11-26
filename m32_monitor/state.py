"""Shared channel-state model used by the simulator and dashboard."""
from dataclasses import asdict,dataclass

@dataclass
class ChannelState:
    number:int
    name:str
    fader:float=0.75
    muted:bool=False
    colour:int=1
    source:int=0
    connected:bool=False
    def as_dict(self):
        return asdict(self)

class ConsoleState:
    def __init__(self):
        self.channels={n:ChannelState(n,"CH %02d"%n,0.72,False,((n-1)%15)+1,n,True) for n in range(1,33)}
        self.online=True
        self.mode="simulator"

    def update(self,address,value):
        parts=address.strip("/").split("/")
        if len(parts)<4 or parts[0]!="ch": return False
        try: channel=self.channels[int(parts[1])]
        except (ValueError,KeyError): return False
        path="/".join(parts[2:])
        if path=="config/name" and isinstance(value,str): channel.name=value
        elif path=="config/color" and isinstance(value,(int,float)): channel.colour=int(value)
        elif path=="config/source" and isinstance(value,(int,float)):
            channel.source=int(value); channel.connected=channel.source>0
        elif path=="mix/fader" and isinstance(value,(int,float)): channel.fader=max(0.0,min(1.0,float(value)))
        elif path=="mix/on" and isinstance(value,(int,float)): channel.muted=int(value)==0
        else: return False
        return True

    def get(self,address):
        parts=address.strip("/").split("/")
        if len(parts)<4 or parts[0]!="ch": return None
        try: channel=self.channels[int(parts[1])]
        except (ValueError,KeyError): return None
        path="/".join(parts[2:])
        return {"config/name":channel.name,"config/color":channel.colour,"config/source":channel.source,
                "mix/fader":channel.fader,"mix/on":0 if channel.muted else 1}.get(path)

    @staticmethod
    def source_label(source):
        if source==0:return "OFF"
        if 1<=source<=32:return "IN%02d"%source
        if 33<=source<=38:return "AUX%d"%(source-32)
        if source==39:return "USB L"
        if source==40:return "USB R"
        if 41<=source<=48:return "FX%d%s"%((source-41)//2+1,"L" if (source-41)%2==0 else "R")
        if 49<=source<=64:return "BUS%02d"%(source-48)
        return "SRC %d"%source

    def visible_channels(self):
        # Hide channels with no input source or an OFF scribble-strip colour.
        return [c.as_dict() for c in self.channels.values() if c.connected and c.colour!=0]
