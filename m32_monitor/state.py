"""Shared console state and effective mute-path calculation."""
from dataclasses import asdict, dataclass, field
import math
import struct
import time
from m32_monitor.routing import CONFIG_LINK_ADDRESSES, ROUTING_PATHS, RoutingState


# Ordered X32node schemas for input strips. Values are (default, minimum, maximum,
# step, kind, enum labels). The community protocol reference is unofficial.
STRIP_NODE_SCHEMA = {
    "bus": {
        "config": {"name": (None, None, None, 0, "string", None), "icon": (1, 1, 74, 1, "int", None),
                   "color": (1, 0, 15, 1, "enum", ("OFF","RD","GN","YE","BL","MG","CY","WH","OFFi","RDi","GNi","YEi","BLi","MGi","CYi","WHi"))},
        "dyn": {"on": (0,0,1,1,"enum",("OFF","ON")), "mode": (0,0,1,1,"enum",("COMP","EXP")),
                "det": (0,0,1,1,"enum",("PEAK","RMS")), "env": (0,0,1,1,"enum",("LIN","LOG")),
                "thr": (-24.0,-60.0,0.0,0.5,"float",None), "ratio": (6,0,11,1,"enum",("1.1","1.3","1.5","2.0","2.5","3.0","4.0","5.0","7.0","10","20","100")),
                "knee": (0.0,0.0,5.0,1.0,"float",None), "mgain": (0.0,0.0,24.0,0.5,"float",None),
                "attack": (10.0,0.0,120.0,1.0,"float",None), "hold": (10.0,0.02,2000.0,0,"float",None),
                "release": (100.0,5.0,4000.0,0,"float",None), "pos": (0,0,1,1,"enum",("PRE","POST")),
                "keysrc": (0,0,64,1,"int",None), "mix": (100.0,0.0,100.0,5.0,"float",None),
                "auto": (0,0,1,1,"enum",("OFF","ON"))},
        "dyn/filter": {"on": (0,0,1,1,"enum",("OFF","ON")), "type": (0,0,8,1,"enum",("LC6","LC12","HC6","HC12","1.0","2.0","3.0","5.0","10.0")),
                        "f": (1000.0,20.0,20000.0,0,"float",None)},
        "insert": {"on": (0,0,1,1,"enum",("OFF","ON")), "pos": (0,0,1,1,"enum",("PRE","POST")),
                   "sel": (0,0,22,1,"enum",("OFF","FX1L","FX1R","FX2L","FX2R","FX3L","FX3R","FX4L","FX4R","FX5L","FX5R","FX6L","FX6R","FX7L","FX7R","FX8L","FX8R","AUX1","AUX2","AUX3","AUX4","AUX5","AUX6"))},
        "eq": {"on": (0,0,1,1,"enum",("OFF","ON"))},
        "mix": {"on": (1,0,1,1,"enum",("OFF","ON")), "fader": (0.75,0.0,1.0,0,"float",None),
                "st": (1,0,1,1,"enum",("OFF","ON")), "pan": (0.0,-100.0,100.0,2.0,"float",None),
                "mono": (0,0,1,1,"enum",("OFF","ON")), "mlevel": (0.75,0.0,1.0,0,"float",None)},
        "grp": {"dca": (0,0,255,1,"int",None), "mute": (0,0,63,1,"int",None)},
    },
    "ch": {
        "config": {"name": (None, None, None, 0, "string", None), "icon": (1, 1, 74, 1, "int", None),
                   "color": (1, 0, 15, 1, "enum", ("OFF","RD","GN","YE","BL","MG","CY","WH","OFFi","RDi","GNi","YEi","BLi","MGi","CYi","WHi")),
                   "source": (0, 0, 64, 1, "int", None)},
        "delay": {"on": (0,0,1,1,"enum",("OFF","ON")), "time": (0.3,0.3,500.0,0.05,"float",None)},
        "preamp": {"trim": (0.0,-18.0,18.0,0,"float",None), "invert": (0,0,1,1,"enum",("OFF","ON")),
                   "hpon": (0,0,1,1,"enum",("OFF","ON")), "hpslope": (1,0,2,1,"enum",("12","18","24")),
                   "hpf": (20.0,20.0,400.0,0,"float",None)},
        "gate": {"on": (0,0,1,1,"enum",("OFF","ON")), "mode": (0,0,4,1,"enum",("EXP2","EXP3","EXP4","GATE","DUCK")),
                 "thr": (-40.0,-80.0,0.0,0.5,"float",None), "range": (60.0,3.0,60.0,1.0,"float",None),
                 "attack": (0.0,0.0,120.0,1.0,"float",None), "hold": (10.0,0.02,2000.0,0,"float",None),
                 "release": (100.0,5.0,4000.0,0,"float",None), "keysrc": (0,0,64,1,"int",None)},
        "gate/filter": {"on": (0,0,1,1,"enum",("OFF","ON")), "type": (0,0,8,1,"enum",("LC6","LC12","HC6","HC12","1.0","2.0","3.0","5.0","10.0")),
                        "f": (1000.0,20.0,20000.0,0,"float",None)},
        "dyn": {"on": (0,0,1,1,"enum",("OFF","ON")), "mode": (0,0,1,1,"enum",("COMP","EXP")),
                "det": (0,0,1,1,"enum",("PEAK","RMS")), "env": (0,0,1,1,"enum",("LIN","LOG")),
                "thr": (-24.0,-60.0,0.0,0.5,"float",None), "ratio": (6,0,11,1,"enum",("1.1","1.3","1.5","2.0","2.5","3.0","4.0","5.0","7.0","10","20","100")),
                "knee": (0.0,0.0,5.0,1.0,"float",None), "mgain": (0.0,0.0,24.0,0.5,"float",None),
                "attack": (10.0,0.0,120.0,1.0,"float",None), "hold": (10.0,0.02,2000.0,0,"float",None),
                "release": (100.0,5.0,4000.0,0,"float",None), "pos": (0,0,1,1,"enum",("PRE","POST")),
                "keysrc": (0,0,64,1,"int",None), "mix": (100.0,0.0,100.0,5.0,"float",None),
                "auto": (0,0,1,1,"enum",("OFF","ON"))},
        "dyn/filter": {"on": (0,0,1,1,"enum",("OFF","ON")), "type": (0,0,8,1,"enum",("LC6","LC12","HC6","HC12","1.0","2.0","3.0","5.0","10.0")),
                        "f": (1000.0,20.0,20000.0,0,"float",None)},
        "insert": {"on": (0,0,1,1,"enum",("OFF","ON")), "pos": (0,0,1,1,"enum",("PRE","POST")),
                   "sel": (0,0,22,1,"enum",("OFF","FX1L","FX1R","FX2L","FX2R","FX3L","FX3R","FX4L","FX4R","FX5L","FX5R","FX6L","FX6R","FX7L","FX7R","FX8L","FX8R","AUX1","AUX2","AUX3","AUX4","AUX5","AUX6"))},
        "eq": {"on": (0,0,1,1,"enum",("OFF","ON"))},
        "mix": {"on": (1,0,1,1,"enum",("OFF","ON")), "fader": (0.75,0.0,1.0,0,"float",None),
                "st": (1,0,1,1,"enum",("OFF","ON")), "pan": (0.0,-100.0,100.0,2.0,"float",None),
                "mono": (0,0,1,1,"enum",("OFF","ON")), "mlevel": (0.75,0.0,1.0,0,"float",None)},
        "grp": {"dca": (0,0,255,1,"int",None), "mute": (0,0,63,1,"int",None)},
        "automix": {"group": (0,0,2,1,"enum",("OFF","X","Y")), "weight": (0.0,-12.0,12.0,0.5,"float",None)}
    },
    "auxin": {
        "config": {"name": (None,None,None,0,"string",None), "icon": (1,1,74,1,"int",None),
                   "color": (1,0,15,1,"enum",("OFF","RD","GN","YE","BL","MG","CY","WH","OFFi","RDi","GNi","YEi","BLi","MGi","CYi","WHi")),
                   "source": (0,0,64,1,"int",None)},
        "preamp": {"trim": (0.0,-18.0,18.0,0,"float",None), "invert": (0,0,1,1,"enum",("OFF","ON"))},
        "eq": {"on": (0,0,1,1,"enum",("OFF","ON"))},
        "mix": {"on": (1,0,1,1,"enum",("OFF","ON")), "fader": (0.75,0.0,1.0,0,"float",None),
                "st": (1,0,1,1,"enum",("OFF","ON")), "pan": (0.0,-100.0,100.0,2.0,"float",None),
                "mono": (0,0,1,1,"enum",("OFF","ON")), "mlevel": (0.75,0.0,1.0,0,"float",None)},
        "grp": {"dca": (0,0,255,1,"int",None), "mute": (0,0,63,1,"int",None)}
    },
    "fxrtn": {
        "config": {"name": (None,None,None,0,"string",None), "icon": (1,1,74,1,"int",None),
                   "color": (1,0,15,1,"enum",("OFF","RD","GN","YE","BL","MG","CY","WH","OFFi","RDi","GNi","YEi","BLi","MGi","CYi","WHi"))},
        "eq": {"on": (0,0,1,1,"enum",("OFF","ON"))},
        "mix": {"on": (1,0,1,1,"enum",("OFF","ON")), "fader": (0.75,0.0,1.0,0,"float",None),
                "st": (1,0,1,1,"enum",("OFF","ON")), "pan": (0.0,-100.0,100.0,2.0,"float",None),
                "mono": (0,0,1,1,"enum",("OFF","ON")), "mlevel": (0.75,0.0,1.0,0,"float",None)},
        "grp": {"dca": (0,0,255,1,"int",None), "mute": (0,0,63,1,"int",None)}
    }
}
for _family in ("ch", "auxin", "fxrtn"):
    _bands = 4
    for _band in range(1, _bands + 1):
        STRIP_NODE_SCHEMA[_family]["eq/%d" % _band] = {
            "type": (2,0,5,1,"enum",("LCut","LShv","PEQ","VEQ","HShv","HCut")),
            "f": (1000.0,20.0,20000.0,0,"float",None),
            "g": (0.0,-15.0,15.0,0.05,"float",None),
            "q": (1.0,0.3,10.0,0,"float",None)}
    for _bus in range(1, 17):
        _send_fields = {"on": (1,0,1,1,"enum",("OFF","ON")),
                        "level": (0.0,0.0,1.0,0,"float",None)}
        if _bus % 2:
            _send_fields.update({"pan": (0.0,-100.0,100.0,2.0,"float",None),
                                 "type": (4,0,5,1,"enum",("IN/LC","<-EQ","EQ->","PRE","POST","GRP")),
                                 "panFollow": (0,0,1,1,"enum",("OFF","ON"))})
        STRIP_NODE_SCHEMA[_family]["mix/%02d" % _bus] = _send_fields

# Bus output strips have six parametric EQ bands and six matrix-send nodes.
for _band in range(1, 7):
    STRIP_NODE_SCHEMA["bus"]["eq/%d" % _band] = {
        "type": (2,0,5,1,"enum",("LCut","LShv","PEQ","VEQ","HShv","HCut")),
        "f": (1000.0,20.0,20000.0,0,"float",None),
        "g": (0.0,-15.0,15.0,0.05,"float",None),
        "q": (1.0,0.3,10.0,0,"float",None)}
for _matrix in range(1, 7):
    _send_fields = {
        "on": (1,0,1,1,"enum",("OFF","ON")),
        "level": (0.0,0.0,1.0,0,"float",None)}
    if _matrix % 2:
        _send_fields.update({
            "pan": (0.0,-100.0,100.0,2.0,"float",None),
            "type": (4,0,5,1,"enum",("IN/LC","<-EQ","EQ->","PRE","POST","GRP")),
            "panFollow": (0,0,1,1,"enum",("OFF","ON"))})
    STRIP_NODE_SCHEMA["bus"]["mix/%02d" % _matrix] = _send_fields

# Matrix output strips: configuration, polarity, dynamics, insert, six-band EQ,
# output level/mute and DCA/mute-group assignments.
STRIP_NODE_SCHEMA["mtx"] = {
    "config": {"name": ("Matrix", None, None, 0, "string", None),
               "icon": (1, 1, 74, 1, "int", None),
               "color": (1, 0, 15, 1, "enum", ("OFF","RD","GN","YE","BL","MG","CY","WH","OFFi","RDi","GNi","YEi","BLi","MGi","CYi","WHi"))},
    "preamp": {"invert": (0,0,1,1,"enum",("OFF","ON"))},
    "config/preamp": {"invert": (0,0,1,1,"enum",("OFF","ON"))},
    "dyn": {"on": (0,0,1,1,"enum",("OFF","ON")), "mode": (0,0,1,1,"enum",("COMP","EXP")),
            "det": (0,0,1,1,"enum",("PEAK","RMS")), "env": (0,0,1,1,"enum",("LIN","LOG")),
            "thr": (-24.0,-60.0,0.0,0.5,"float",None),
            "ratio": (6,0,11,1,"enum",("1.1","1.3","1.5","2.0","2.5","3.0","4.0","5.0","7.0","10","20","100")),
            "knee": (0.0,0.0,5.0,1.0,"float",None), "mgain": (0.0,0.0,24.0,0.5,"float",None),
            "attack": (10.0,0.0,120.0,1.0,"float",None), "hold": (10.0,0.02,2000.0,0,"float",None),
            "release": (100.0,5.0,4000.0,0,"float",None), "pos": (0,0,1,1,"enum",("PRE","POST")),
            "mix": (100.0,0.0,100.0,5.0,"float",None), "auto": (0,0,1,1,"enum",("OFF","ON"))},
    "dyn/filter": {"on": (0,0,1,1,"enum",("OFF","ON")),
                   "type": (0,0,8,1,"enum",("LC6","LC12","HC6","HC12","1.0","2.0","3.0","5.0","10.0")),
                   "f": (1000.0,20.0,20000.0,0,"float",None)},
    "insert": {"on": (0,0,1,1,"enum",("OFF","ON")), "pos": (0,0,1,1,"enum",("PRE","POST")),
               "sel": (0,0,22,1,"enum",("OFF","FX1L","FX1R","FX2L","FX2R","FX3L","FX3R","FX4L","FX4R","FX5L","FX5R","FX6L","FX6R","FX7L","FX7R","FX8L","FX8R","AUX1","AUX2","AUX3","AUX4","AUX5","AUX6"))},
    "eq": {"on": (0,0,1,1,"enum",("OFF","ON"))},
    "mix": {"on": (1,0,1,1,"enum",("OFF","ON")), "fader": (0.75,0.0,1.0,0,"float",None)},
    "grp": {"dca": (0,0,255,1,"int",None), "mute": (0,0,63,1,"int",None)},
}
for _band in range(1, 7):
    STRIP_NODE_SCHEMA["mtx"]["eq/%d" % _band] = {
        "type": (2,0,13,1,"enum",("LCut","LShv","PEQ","VEQ","HShv","HCut","BU6","BU12","BS12","LR12","BU18","BU24","BS24","LR24")),
        "f": (1000.0,20.0,20000.0,0,"float",None),
        "g": (0.0,-15.0,15.0,0.05,"float",None),
        "q": (1.0,0.3,10.0,0,"float",None)}


# Main stereo and mono output processing nodes.
MAIN_NODE_SCHEMA = {
    "config": {"name": ("Main L/R", None, None, 0, "string", None),
               "icon": (1, 1, 74, 1, "int", None),
               "color": (1, 0, 15, 1, "enum", ("OFF","RD","GN","YE","BL","MG","CY","WH","OFFi","RDi","GNi","YEi","BLi","MGi","CYi","WHi"))},
    "dyn": {
        "on": (0,0,1,1,"enum",("OFF","ON")), "mode": (0,0,1,1,"enum",("COMP","EXP")),
        "det": (0,0,1,1,"enum",("PEAK","RMS")), "env": (0,0,1,1,"enum",("LIN","LOG")),
        "thr": (-24.0,-60.0,0.0,0.5,"float",None),
        "ratio": (6,0,11,1,"enum",("1.1","1.3","1.5","2.0","2.5","3.0","4.0","5.0","7.0","10","20","100")),
        "knee": (0.0,0.0,5.0,1.0,"float",None), "mgain": (0.0,0.0,24.0,0.5,"float",None),
        "attack": (10.0,0.0,120.0,1.0,"float",None), "hold": (10.0,0.02,2000.0,0,"float",None),
        "release": (100.0,5.0,4000.0,0,"float",None), "pos": (0,0,1,1,"enum",("PRE","POST")),
        "mix": (100.0,0.0,100.0,5.0,"float",None), "auto": (0,0,1,1,"enum",("OFF","ON"))},
    "dyn/filter": STRIP_NODE_SCHEMA["bus"]["dyn/filter"],
    "insert": STRIP_NODE_SCHEMA["bus"]["insert"],
    "eq": STRIP_NODE_SCHEMA["bus"]["eq"],
    "mix": {"on": (1,0,1,1,"enum",("OFF","ON")), "fader": (0.75,0.0,1.0,0,"float",None), "pan": (0.0,-100.0,100.0,2.0,"float",None)},
    "grp": STRIP_NODE_SCHEMA["bus"]["grp"],
}
for _band in range(1, 7):
    MAIN_NODE_SCHEMA["eq/%d" % _band] = STRIP_NODE_SCHEMA["bus"]["eq/%d" % _band]

# Main output matrix sends use the extended five-field M32 send format.
for _matrix in range(1, 7):
    MAIN_NODE_SCHEMA["mix/%02d" % _matrix] = {
        "on": (1,0,1,1,"enum",("OFF","ON")),
        "level": (0.0,0.0,1.0,0,"float",None),
        "pan": (0.0,-100.0,100.0,2.0,"float",None),
        "type": (4,0,5,1,"enum",("IN/LC","<-EQ","EQ->","PRE","POST","GRP")),
        "panFollow": (0,0,1,1,"enum",("OFF","ON"))}

# Main L/R and Mono/Centre matrix sends follow the M32 send layout:
# odd-numbered sends carry pan, tap type and pan-follow as well as level.
for _matrix in range(1, 7):
    _send_fields = {
        "on": (1,0,1,1,"enum",("OFF","ON")),
        "level": (0.0,0.0,1.0,0,"float",None)}
    if _matrix % 2:
        _send_fields.update({
            "pan": (0.0,-100.0,100.0,2.0,"float",None),
            "type": (4,0,5,1,"enum",("IN/LC","<-EQ","EQ->","PRE","POST","GRP")),
            "panFollow": (0,0,1,1,"enum",("OFF","ON"))})
    MAIN_NODE_SCHEMA["mix/%02d" % _matrix] = _send_fields

# Mono/Centre master mix has no pan field; retain all shared processing and
# matrix-send nodes, but use a two-field master mix node.
MAIN_MONO_NODE_SCHEMA = dict(MAIN_NODE_SCHEMA)
MAIN_MONO_NODE_SCHEMA["mix"] = {
    "on": MAIN_NODE_SCHEMA["mix"]["on"],
    "fader": MAIN_NODE_SCHEMA["mix"]["fader"],
}


@dataclass
class ChannelState:
    number: int
    name: str
    fader: float = 0.75
    muted: bool = False
    colour: int = 1
    source: int = 0
    connected: bool = False
    dca_mask: int = 0
    mute_mask: int = 0
    main_st: bool = True
    main_mono: bool = False
    main_mono_level: float = 1.0
    sends: dict = field(default_factory=dict)
    send_types: dict = field(default_factory=dict)

    def as_dict(self):
        return asdict(self)


class ConsoleState:
    """Normalised snapshot of the console parameters relevant to signal muting."""

    def __init__(self):
        self.channels = {
            n: ChannelState(n, "CH %02d" % n, 0.72, False,
                            ((n - 1) % 15) + 1, n, True)
            for n in range(1, 33)
        }
        self.mode = "simulator"
        self.routing = RoutingState()
        self.meters = {}
        self.preferences = {"rta/visibility": 0, "rta/gain": 0.0, "rta/autogain": 0, "rta/source": 0, "rta/pos": 0, "rta/mode": 0, "rta/options": 0, "rta/det": 0, "rta/decay": 0.0, "rta/peakhold": 0}
        self.rta_status = {"rtamodeeq": 0, "rtamodegeq": 0, "rtaeqpre": 0, "rtageqpost": 0, "rtasource": 0}
        # X-Live! recorder status. Defaults describe no mounted SD cards and no session.
        self.urec = {
            "sessionmax": 0, "markermax": 0, "sessionlen": 0, "sessionpos": 0,
            "markerpos": 0, "batterystate": 0, "srate": 0, "tracks": 0,
            "sessionspan": 0, "sessionoffs": 0, "sd1state": 0, "sd2state": 0,
            "sd1info": "Insert SD Card.", "sd2info": "Insert SD Card.",
            "errormessage": "", "errorcode": 0,
        }
        self.urec_sessions = {}
        self.urec_markers = {}
        self.urec_status = {"state": 0, "etime": 0, "rtime": 0}
        self.config_links = {
            "chlink": {f"{n}-{n+1}": 0 for n in range(1, 32, 2)},
            "auxlink": {f"{n}-{n+1}": 0 for n in range(1, 8, 2)},
            "fxlink": {f"{n}-{n+1}": 0 for n in range(1, 8, 2)},
            "buslink": {f"{n}-{n+1}": 0 for n in range(1, 16, 2)},
            "mtxlink": {f"{n}-{n+1}": 0 for n in range(1, 6, 2)},
        }
        self.link_config = {"hadly": 0, "eq": 0, "dyn": 0, "fdrmute": 0}
        # Main mono/centre output configuration: 0=LR+M, 1=LCR; link is OFF/ON.
        self.mono_config = {"mode": 0, "link": 0}
        # Talkback levels are stored in dB; destination maps are 18-bit masks.
        self.talk_config = {"enable": 0, "source": 0,
            "A": {"level": 0.0, "dim": 0, "latch": 0, "destmap": 0},
            "B": {"level": 0.0, "dim": 0, "latch": 0, "destmap": 0}}
        # Oscillator generator configuration; frequency values use 121 logarithmic positions.
        self.osc_config = {"level": 0.0, "f1": 632.456, "f2": 632.456, "fsel": 0, "type": 0, "dest": 0}
        # User routing slots: outputs 01-48 (sources 0-208), inputs 01-32 (sources 0-168).
        self.user_rout_out = {number: 0 for number in range(1, 49)}
        self.user_rout_in = {number: 0 for number in range(1, 33)}
        # User-assignable surface banks A/B/C: colour, four encoders and eight buttons.
        self.user_controls = {
            bank: {"color": 0, "enc": {n: "-" for n in range(1, 5)},
                   "btn": {n: "-" for n in range(5, 13)}}
            for bank in ("A", "B", "C")
        }
        self.tape_config = {"gainL": 0.0, "gainR": 0.0, "autoplay": 0}
        self.amix_enable = {"X": 0, "Y": 0}
        self.dp48_config = {
            "scope": 0, "broadcast": 0, "aesAB": 0,
            "link": {n: 0 for n in range(1, 25)},
            "assign": {n: 0 for n in range(1, 49)},
            "grpname": {n: "" for n in range(1, 13)},
        }
        self.solo_config = {
            "level": 0.0, "source": 0, "sourcetrim": 0.0,
            "chmode": 0, "busmode": 0, "dcamode": 0,
            "exclusive": 0, "followsel": 0, "followsolo": 0,
            "dimatt": -20.0, "dim": 0, "mono": 0, "delay": 0,
            "delaytime": 0.3, "masterctrl": 0, "mute": 0, "dimpfl": 0,
        }
        self.key_solo = 0
        self.solo_switches = {number: 0 for number in range(1, 81)}
        self.card_preferences = {name: 0 for name in ("UFifc", "UFmode", "USBmode", "ADATwc", "ADATsync", "MADImode", "MADIin", "MADIout", "MADIsrc", "URECtracks", "URECplayb", "URECrout", "URECsdsel")}
        # Preserve M32-Edit showfile, miscellaneous preference and action-option values.
        self.misc_nodes = {}
        self.received = set()
        self.last_seen = time.monotonic()
        self.auxins = {n: ChannelState(n, "AUX %02d" % n, 0.72, False, 1, 32 + n, False) for n in range(1, 9)}
        self.fx_returns = {n: ChannelState(n, "FX RTN %02d" % n, 0.72, False, 1, 0, False) for n in range(1, 9)}
        self.strip_node_schema = STRIP_NODE_SCHEMA
        self.main_node_schema = MAIN_NODE_SCHEMA
        self.main_mono_node_schema = MAIN_MONO_NODE_SCHEMA
        self.strip_nodes = {}
        for family, nodes in STRIP_NODE_SCHEMA.items():
            counts = {"ch": 32, "auxin": 8, "fxrtn": 8, "bus": 16, "mtx": 6}[family]
            for number in range(1, counts + 1):
                for node, fields in nodes.items():
                    for field_name, spec in fields.items():
                        default = spec[0]
                        self.strip_nodes["/%s/%02d/%s/%s" % (family, number, node, field_name)] = default
        self.dcas = {
            n: {"number": n, "name": "DCA %d" % n, "icon": 1, "colour": 1, "on": True, "fader": 0.75}
            for n in range(1, 9)
        }
        self.fx = {
            n: {"type": 0, "source_l": 0, "source_r": 0,
                "par": {p: 0.0 for p in range(1, 65)}}
            for n in range(1, 9)
        }
        self.mute_groups = {n: False for n in range(1, 7)}
        self.dca_mutes_enabled = None
        self.hard_mutes_enabled = None
        self.buses = {
            n: {"number": n, "name": "Bus %02d" % n, "icon": 1, "colour": 1, "on": True, "fader": 0.75, "dca_mask": 0, "mute_mask": 0}
            for n in range(1, 17)
        }
        self.outputs = {
            "main_st": {"on": True, "fader": 0.75, "pan": 0.0, "dca_mask": 0, "mute_mask": 0, "sends": {}},
            "main_mono": {"on": True, "fader": 0.75, "pan": 0.0, "dca_mask": 0, "mute_mask": 0, "sends": {}},
        }
        # Sixteen physical XLR output sockets, independently patchable.
        self.output_main = {
            n: {"src": 0, "pos": 8, "invert": 0, "delay_on": 0, "delay_time": 0.3}
            for n in range(1, 17)
        }
        # Six physical 1/4-inch auxiliary output sockets.
        self.output_aux = {
            n: {"src": 0, "pos": 8, "invert": 0}
            for n in range(1, 7)
        }
        # Sixteen Ultranet/P16 personal-monitor output assignments.
        self.output_p16 = {
            n: {"src": 0, "pos": 8, "invert": 0, "iq_group": 0, "iq_speaker": 0}
            for n in range(1, 17)
        }
        # Remote headamps: local XLR (000-031), AES50 A (032-079), AES50 B (080-127).
        self.headamps = {
            n: {"gain": 0.0, "phantom": 0}
            for n in range(128)
        }
        # Two AES50 output banks and two recording-card output banks.
        self.output_aes = {
            n: {"src": 0, "pos": 8, "invert": 0}
            for n in range(1, 3)
        }
        self.output_rec = {
            n: {"src": 0, "pos": 8}
            for n in range(1, 3)
        }
        for prefix, schema in (("/main/st", MAIN_NODE_SCHEMA), ("/main/m", MAIN_MONO_NODE_SCHEMA)):
            for node, fields in schema.items():
                for field_name, spec in fields.items():
                    self.strip_nodes["%s/%s/%s" % (prefix, node, field_name)] = spec[0]
        self.matrices = {n: {"number": n, "name": "Matrix %02d" % n, "icon": 1, "colour": 1,
                             "on": True, "fader": 0.75, "dca_mask": 0, "mute_mask": 0}
                         for n in range(1, 7)}

    @property
    def online(self):
        if self.mode == "simulator":
            return True
        return self.last_seen is not None and time.monotonic() - self.last_seen < 15

    def mark_seen(self):
        self.last_seen = time.monotonic()

    @staticmethod
    def _bool(value):
        return bool(int(value))

    def update_meter(self, address, blob):
        """Decode the documented M32 meter blob format without guessing malformed packets."""
        if not address.startswith("/meters/") or not isinstance(blob, (bytes, bytearray)):
            return False
        payload = bytes(blob)
        if len(payload) < 8:
            return False
        byte_length = struct.unpack(">I", payload[:4])[0]
        count = struct.unpack("<I", payload[4:8])[0]
        if count > 512 or byte_length > len(payload) - 4 or 8 + count * 4 > len(payload):
            return False
        values = struct.unpack("<%df" % count, payload[8:8 + count * 4]) if count else ()
        self.meters[address.rsplit("/", 1)[-1]] = {
            "values": [max(0.0, float(value)) for value in values],
            "received_at": time.time(),
        }
        return True

    def meters_snapshot(self):
        return {"streams": [{"id": key, "count": len(item["values"]),
                             "values": item["values"], "received_at": item["received_at"]}
                            for key, item in sorted(self.meters.items())]}

    def update(self, address, value):
        if self.mode == "simulator" and address in ROUTING_PATHS:
                choices = ROUTING_PATHS[address][1]
                if (isinstance(value, bool) or not isinstance(value, (int, float))
                        or float(value) != int(value) or not 0 <= int(value) < len(choices)):
                    return False
        if address not in CONFIG_LINK_ADDRESSES and not address.startswith(("/config/solo/", "/config/talk/", "/config/userrout/", "/fx/", "/outputs/main/", "/outputs/aux/", "/outputs/p16/", "/outputs/aes/", "/outputs/rec/")) and self.routing.update(address, value):
            self.received.add(address)
            return True
        parts = address.strip("/").split("/")
        try:
            if len(parts) == 2 and parts[0] == "-urec":
                field = parts[1]
                if field not in self.urec:
                    return False
                if field in ("sd1info", "sd2info", "errormessage"):
                    if not isinstance(value, str) or len(value) > 256:
                        return False
                else:
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) != int(value) or int(value) < 0:
                        return False
                    if field in ("batterystate", "sd1state", "sd2state") and int(value) not in range(4 if field != "batterystate" else 3):
                        return False
                    value = int(value)
                self.urec[field] = value
                self.received.add(address)
                return True
            if len(parts) >= 4 and parts[0] in ("ch", "auxin", "fxrtn"):
                collection = {"ch": self.channels, "auxin": self.auxins, "fxrtn": self.fx_returns}[parts[0]]
                channel = collection[int(parts[1])]
                path = "/".join(parts[2:])
                if address in self.strip_nodes and not self._valid_strip_node_value(address, value):
                    return False
                if path == "config/name" and isinstance(value, str) and len(value) <= 12:
                    channel.name = value
                elif path == "config/color" and isinstance(value, (int, float)) and not isinstance(value, bool) and float(value).is_integer() and 0 <= int(value) <= 15:
                    channel.colour = int(value)
                elif path == "config/source" and isinstance(value, (int, float)) and not isinstance(value, bool) and float(value).is_integer() and 0 <= int(value) <= 64 and parts[0] != "fxrtn":
                    channel.source = int(value)
                    channel.connected = channel.source > 0
                elif path == "mix/fader" and isinstance(value, (int, float)):
                    channel.fader = max(0.0, min(1.0, float(value)))
                elif path == "mix/on" and isinstance(value, (int, float)):
                    channel.muted = int(value) == 0
                elif path == "mix/st" and isinstance(value, (int, float)):
                    channel.main_st = self._bool(value)
                elif path == "mix/mono" and isinstance(value, (int, float)):
                    channel.main_mono = self._bool(value)
                elif path == "mix/mlevel" and isinstance(value, (int, float)):
                    channel.main_mono_level = max(0.0, min(1.0, float(value)))
                elif path == "grp/dca" and isinstance(value, (int, float)):
                    channel.dca_mask = int(value) & 255
                elif path == "grp/mute" and isinstance(value, (int, float)):
                    channel.mute_mask = int(value) & 63
                elif len(parts) == 5 and parts[2] == "mix" and parts[3].isdigit():
                    bus = int(parts[3])
                    if not 1 <= bus <= 16:
                        return False
                    send = channel.sends.setdefault(bus, {"on": True, "level": 0.0})
                    if parts[4] == "type" and isinstance(value, (int, float)):
                        channel.send_types[bus] = int(value)
                    elif parts[4] == "level" and isinstance(value, (int, float)):
                        send["level"] = max(0.0, min(1.0, float(value)))
                    elif parts[4] == "on" and isinstance(value, (int, float)):
                        send["on"] = self._bool(value)
                    elif address in self.strip_nodes:
                        self.strip_nodes[address] = value
                    else:
                        return False
                else:
                    if address not in self.strip_nodes or not self._valid_strip_node_value(address, value):
                        return False
                    self.strip_nodes[address] = value
                if parts[0] == "fxrtn" and path == "config/color":
                    channel.connected = channel.colour != 0
                self.received.add(address)
                return True

            if len(parts) >= 3 and parts[0] == "fx":
                number = int(parts[1])
                if number not in self.fx:
                    return False
                fx = self.fx[number]
                field = parts[2:]
                if field == ["type"]:
                    maximum = 60 if number <= 4 else 33
                    if (isinstance(value, bool) or not isinstance(value, (int, float))
                            or float(value) != int(value) or not 0 <= int(value) <= maximum):
                        return False
                    fx["type"] = int(value)
                elif field in (["source", "l"], ["source", "r"]):
                    if number > 4 or isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) != int(value) or not 0 <= int(value) <= 17:
                        return False
                    fx["source_l" if field[-1] == "l" else "source_r"] = int(value)
                elif len(field) == 2 and field[0] == "par" and field[1].isdigit():
                    parameter = int(field[1])
                    if not 1 <= parameter <= 64 or isinstance(value, bool):
                        return False
                    if isinstance(value, (int, float)):
                        if not math.isfinite(float(value)):
                            return False
                        fx["par"][parameter] = float(value)
                    elif isinstance(value, str) and value and len(value) <= 32:
                        fx["par"][parameter] = value
                    else:
                        return False
                else:
                    return False
                self.received.add(address)
                return True

            if len(parts) == 3 and parts[0] == "headamp" and parts[1].isdigit():
                number = int(parts[1])
                if number not in self.headamps or parts[2] not in ("gain", "phantom"):
                    return False
                if parts[2] == "gain":
                    if (isinstance(value, bool) or not isinstance(value, (int, float))
                            or not math.isfinite(float(value)) or not -12.0 <= float(value) <= 60.0
                            or abs(float(value) * 2 - round(float(value) * 2)) > 1e-6):
                        return False
                    self.headamps[number]["gain"] = float(value)
                else:
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) not in (0.0, 1.0):
                        return False
                    self.headamps[number]["phantom"] = int(value)
                self.received.add(address)
                return True

            if len(parts) >= 4 and parts[0] == "outputs" and parts[1] in ("main", "aux", "p16", "aes", "rec"):
                collection = {"main": self.output_main, "aux": self.output_aux, "p16": self.output_p16, "aes": self.output_aes, "rec": self.output_rec}[parts[1]]
                number = int(parts[2])
                if number not in collection:
                    return False
                output = collection[number]
                field = parts[3:]
                if field == ["src"]:
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) != int(value) or not 0 <= int(value) <= 76: return False
                    output["src"] = int(value)
                elif field == ["pos"]:
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) != int(value) or not 0 <= int(value) <= 8: return False
                    output["pos"] = int(value)
                elif field == ["invert"] and parts[1] in ("main", "aux", "p16", "aes"):
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) not in (0.0, 1.0): return False
                    output["invert"] = int(value)
                elif parts[1] == "p16" and field == ["iQ", "group"]:
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) != int(value) or not 0 <= int(value) <= 2: return False
                    output["iq_group"] = int(value)
                elif parts[1] == "p16" and field == ["iQ", "speaker"]:
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) != int(value) or not 0 <= int(value) <= 6: return False
                    output["iq_speaker"] = int(value)
                elif parts[1] == "main" and field == ["delay", "on"]:
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) not in (0.0, 1.0): return False
                    output["delay_on"] = int(value)
                elif parts[1] == "main" and field == ["delay", "time"]:
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not 0.3 <= float(value) <= 500.0 or abs((float(value)-0.3)/0.1-round((float(value)-0.3)/0.1)) > 1e-6: return False
                    output["delay_time"] = float(value)
                else:
                    return False
                self.received.add(address)
                return True

            if len(parts) >= 3 and parts[0] == "dca":
                number = int(parts[1])
                if number not in self.dcas:
                    return False
                dca = self.dcas[number]
                field = "/".join(parts[2:])
                if field == "on":
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) not in (0.0, 1.0):
                        return False
                    dca["on"] = bool(int(value))
                elif field == "fader":
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
                        return False
                    dca["fader"] = float(value)
                elif field == "config/name":
                    if not isinstance(value, str) or len(value) > 12:
                        return False
                    dca["name"] = value
                elif field == "config/icon":
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) != int(value) or not 1 <= int(value) <= 74:
                        return False
                    dca["icon"] = int(value)
                elif field == "config/color":
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) != int(value) or not 0 <= int(value) <= 15:
                        return False
                    dca["colour"] = int(value)
                else:
                    return False
                self.received.add(address)
                return True

            if len(parts) == 5 and parts[0] == "main" and parts[1] in ("st", "m") and parts[2] == "mix":
                matrix = int(parts[3])
                schema = MAIN_MONO_NODE_SCHEMA if parts[1] == "m" else MAIN_NODE_SCHEMA
                if not 1 <= matrix <= 6 or parts[4] not in schema["mix/%02d" % matrix] or not self._valid_main_node_value(address, value):
                    return False
                output_key = "main_st" if parts[1] == "st" else "main_mono"
                default_send = {"on": 1, "level": 0.0}
                if matrix % 2:
                    default_send.update({"pan": 0.0, "type": 4, "panFollow": 0})
                send = self.outputs[output_key].setdefault("sends", {}).setdefault(matrix, default_send)
                send[parts[4]] = int(value) if parts[4] in ("on", "type", "panFollow") else float(value)
                self.strip_nodes[address] = value
                self.received.add(address)
                return True

            if len(parts) >= 4 and parts[0] == "mtx":
                number = int(parts[1])
                if number not in self.matrices or address not in self.strip_nodes:
                    return False
                if not self._valid_strip_node_value(address, value):
                    return False
                self.strip_nodes[address] = value
                matrix = self.matrices[number]
                field_path = parts[2:]
                if field_path == ["config", "name"]: matrix["name"] = value
                elif field_path == ["config", "icon"]: matrix["icon"] = int(value)
                elif field_path == ["config", "color"]: matrix["colour"] = int(value)
                elif field_path in (["preamp", "invert"], ["config", "preamp", "invert"]):
                    alias = "/mtx/%02d/" % number
                    self.strip_nodes[alias + "preamp/invert"] = int(value)
                    self.strip_nodes[alias + "config/preamp/invert"] = int(value)
                elif field_path == ["mix", "on"]: matrix["on"] = self._bool(value)
                elif field_path == ["mix", "fader"]: matrix["fader"] = float(value)
                elif field_path == ["grp", "dca"]: matrix["dca_mask"] = int(value)
                elif field_path == ["grp", "mute"]: matrix["mute_mask"] = int(value)
                self.received.add(address)
                return True

            if len(parts) == 3 and parts[:2] == ["config", "mono"]:
                field = parts[2]
                maximum = 1
                if field not in self.mono_config or isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) != int(value) or int(value) not in range(maximum + 1):
                    return False
                self.mono_config[field] = int(value)
                self.received.add(address)
                return True

            if len(parts) == 4 and parts[:3] in (["config", "userrout", "out"], ["config", "userrout", "in"]):
                direction = parts[2]
                slots = self.user_rout_out if direction == "out" else self.user_rout_in
                max_source = 208 if direction == "out" else 168
                slot_text = parts[3]
                if not slot_text.isdigit() or len(slot_text) != 2:
                    return False
                slot = int(slot_text)
                if slot not in slots or isinstance(value, bool) or not isinstance(value, (int, float)):
                    return False
                number = float(value)
                if number != int(number) or not 0 <= number <= max_source:
                    return False
                slots[slot] = int(number)
                self.received.add(address)
                return True

            if len(parts) in (4, 5) and parts[:2] == ["config", "userctrl"]:
                bank, section, slot_text = parts[2], parts[3], None
                if bank not in self.user_controls:
                    return False
                if section == "color" and len(parts) == 4:
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) != int(value) or int(value) not in range(16):
                        return False
                    self.user_controls[bank]["color"] = int(value)
                elif section in ("enc", "btn") and len(parts) == 5:
                    slot_text = parts[4]
                    values = self.user_controls[bank][section]
                    if not slot_text.isdigit() or int(slot_text) not in values or not isinstance(value, str) or len(value) > 7:
                        return False
                    values[int(slot_text)] = value
                else:
                    return False
                self.received.add(address)
                return True

            if len(parts) == 3 and parts[:2] == ["config", "tape"]:
                field = parts[2]
                if field == "autoplay":
                    valid = not isinstance(value, bool) and isinstance(value, (int, float)) and float(value) in (0.0, 1.0)
                else:
                    valid = field in ("gainL", "gainR") and not isinstance(value, bool) and isinstance(value, (int, float)) and -6.0 <= float(value) <= 24.0 and abs(float(value) * 2 - round(float(value) * 2)) < 1e-6
                if not valid:
                    return False
                self.tape_config[field] = int(value) if field == "autoplay" else float(value)
                self.received.add(address)
                return True

            if len(parts) == 3 and parts[:2] == ["config", "amixenable"]:
                field = parts[2]
                if field not in self.amix_enable or isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) not in (0.0, 1.0):
                    return False
                self.amix_enable[field] = int(value)
                self.received.add(address)
                return True

            if len(parts) >= 3 and parts[:2] == ["config", "dp48"]:
                field = parts[2]
                if len(parts) == 3 and field in ("scope", "broadcast", "aesAB"):
                    maximum = 15 if field == "scope" else 1
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) != int(value) or int(value) not in range(maximum + 1):
                        return False
                    self.dp48_config[field] = 0 if field == "broadcast" else int(value)
                elif len(parts) == 4 and field in ("link", "assign", "grpname"):
                    slot_text = parts[3]
                    values = self.dp48_config[field]
                    if not slot_text.isdigit() or len(slot_text) != 2 or int(slot_text) not in values:
                        return False
                    if field == "grpname":
                        if not isinstance(value, str) or len(value) > 8:
                            return False
                        values[int(slot_text)] = value
                    else:
                        maximum = 1 if field == "link" else 12
                        if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) != int(value) or int(value) not in range(maximum + 1):
                            return False
                        values[int(slot_text)] = int(value)
                else:
                    return False
                self.received.add(address)
                return True

            if len(parts) == 3 and parts[:2] == ["config", "osc"]:
                field = parts[2]
                if field not in self.osc_config or isinstance(value, bool) or not isinstance(value, (int, float)):
                    return False
                number = float(value)
                if field == "level":
                    valid = -90.0 <= number <= 10.0 and abs((number + 90.0) / 0.625 - round((number + 90.0) / 0.625)) < 1e-6
                elif field in ("f1", "f2"):
                    # Console frequency strings such as 1k00 need not land exactly on
                    # the simulator's nominal slider grid.
                    valid = 20.0 <= number <= 20000.0
                elif field == "fsel":
                    valid = number in (0.0, 1.0)
                elif field == "type":
                    valid = number in (0.0, 1.0, 2.0)
                else:
                    valid = number == int(number) and 0 <= number <= 25
                if not valid:
                    return False
                self.osc_config[field] = int(number) if field in ("fsel", "type", "dest") else number
                self.received.add(address)
                return True

            if len(parts) == 3 and parts[:2] == ["config", "talk"]:
                field = parts[2]
                if field not in ("enable", "source") or isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) not in (0.0, 1.0):
                    return False
                self.talk_config[field] = int(value)
                self.received.add(address)
                return True

            if len(parts) == 4 and parts[:2] == ["config", "talk"] and parts[2] in ("A", "B"):
                section, field = parts[2], parts[3]
                if field not in self.talk_config[section] or isinstance(value, bool) or not isinstance(value, (int, float)):
                    return False
                number = float(value)
                if field in ("dim", "latch"):
                    valid = number in (0.0, 1.0)
                elif field == "destmap":
                    valid = number == int(number) and 0 <= number <= 262143
                else:
                    valid = -90.0 <= number <= 10.0 and abs((number + 90.0) / 0.625 - round((number + 90.0) / 0.625)) < 1e-6
                if not valid:
                    return False
                self.talk_config[section][field] = int(number) if field in ("dim", "latch", "destmap") else number
                self.received.add(address)
                return True

            if len(parts) == 3 and parts[:2] == ["config", "solo"]:
                field = parts[2]
                if field not in self.solo_config or isinstance(value, bool) or not isinstance(value, (int, float)):
                    return False
                number = float(value)
                if field == "source":
                    valid = number == int(number) and 0 <= number <= 6
                elif field in ("chmode", "busmode", "dcamode", "exclusive", "followsel",
                               "followsolo", "dim", "mono", "delay", "masterctrl", "mute", "dimpfl"):
                    valid = number in (0, 1) and number == int(number)
                elif field == "sourcetrim":
                    valid = -18 <= number <= 18 and abs(number * 2 - round(number * 2)) < 1e-6
                elif field == "dimatt":
                    valid = -40 <= number <= 0 and number == int(number)
                elif field == "delaytime":
                    valid = 0.3 <= number <= 500 and abs(number * 10 - round(number * 10)) < 1e-6
                else:
                    valid = -90 <= number <= 10 and abs((number + 90) / 0.625 - round((number + 90) / 0.625)) < 1e-6
                if not valid:
                    return False
                self.solo_config[field] = int(number) if field in (
                    "source", "chmode", "busmode", "dcamode", "exclusive", "followsel",
                    "followsolo", "dim", "mono", "delay", "masterctrl", "mute", "dimpfl"
                ) else number
                self.received.add(address)
                return True

            if len(parts) == 3 and parts[:2] == ["config", "linkcfg"]:
                field = parts[2]
                if field not in self.link_config or isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) not in (0, 1) or float(value) != int(value):
                    return False
                self.link_config[field] = int(value)
                self.received.add(address)
                return True

            if len(parts) == 3 and parts[0] == "config" and parts[1] in self.config_links:
                family, pair = parts[1], parts[2]
                if pair not in self.config_links[family] or isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) not in (0, 1) or float(value) != int(value):
                    return False
                self.config_links[family][pair] = int(value)
                self.routing.values[address] = int(value)
                self.received.add(address)
                return True

            if address == "/-prefs/rta/visibility" and isinstance(value, (int, float)) and float(value) == int(value) and 0 <= int(value) <= 12:
                self.preferences["rta/visibility"] = int(value)
                self.received.add(address)
                return True

            if address in ("/-prefs/rta/options", "/-prefs/rta/option") and isinstance(value, (int, float)) and float(value) == int(value) and 0 <= int(value) <= 63:
                self.preferences["rta/options"] = int(value)
                self.received.add(address)
                return True

            if address == "/-prefs/rta/det" and isinstance(value, (int, float)) and float(value) == int(value) and int(value) in (0, 1):
                self.preferences["rta/det"] = int(value)
                self.received.add(address)
                return True

            if address == "/-prefs/rta/decay" and isinstance(value, (int, float)) and 0.0 <= float(value) <= 1.0 and abs(float(value) * 18 - round(float(value) * 18)) < 1e-6:
                self.preferences["rta/decay"] = round(float(value), 4)
                self.received.add(address)
                return True

            if address == "/-prefs/rta/peakhold" and isinstance(value, (int, float)) and float(value) == int(value) and int(value) in range(9):
                self.preferences["rta/peakhold"] = int(value)
                self.received.add(address)
                return True

            if address.startswith("/-stat/") and address.rsplit("/", 1)[-1] in self.rta_status:
                key = address.rsplit("/", 1)[-1]
                maximum = 170 if key == "rtasource" else 1
                if isinstance(value, (int, float)) and float(value) == int(value) and 0 <= int(value) <= maximum:
                    self.rta_status[key] = int(value)
                    self.received.add(address)
                    return True
                return False

            if len(parts) == 3 and parts[:2] == ["-stat", "solosw"] and parts[2].isdigit():
                number = int(parts[2])
                if number not in self.solo_switches or not isinstance(value, (int, float)) or int(value) not in (0, 1) or float(value) != int(value):
                    return False
                self.solo_switches[number] = int(value)
                self.received.add(address)
                return True

            if len(parts) == 3 and parts[:2] == ["-prefs", "card"] and parts[2] in self.card_preferences and isinstance(value, (int, float)) and float(value) == int(value):
                self.card_preferences[parts[2]] = int(value)
                self.received.add(address)
                return True

            if address == "/-stat/keysolo" and isinstance(value, (int, float)) and int(value) in (0, 1) and float(value) == int(value):
                self.key_solo = int(value)
                self.received.add(address)
                return True

            if address == "/-prefs/rta/source" and isinstance(value, (int, float)) and float(value) == int(value) and 0 <= int(value) <= 73:
                self.preferences["rta/source"] = int(value)
                self.received.add(address)
                return True

            if address == "/-prefs/rta/pos" and isinstance(value, (int, float)) and float(value) == int(value) and int(value) in (0, 1):
                self.preferences["rta/pos"] = int(value)
                self.received.add(address)
                return True

            if address == "/-prefs/rta/mode" and isinstance(value, (int, float)) and float(value) == int(value) and int(value) in (0, 1):
                self.preferences["rta/mode"] = int(value)
                self.received.add(address)
                return True

            if address == "/-prefs/rta/autogain" and isinstance(value, (int, float)) and int(value) in (0, 1) and float(value) == int(value):
                self.preferences["rta/autogain"] = int(value)
                self.received.add(address)
                return True

            if (address == "/-prefs/rta/gain" and isinstance(value, (int, float))
                    and 0.0 <= float(value) <= 1.0
                    and abs(float(value) * 10 - round(float(value) * 10)) < 1e-6):
                self.preferences["rta/gain"] = round(float(value), 3)
                self.received.add(address)
                return True

            if address in ("/-prefs/dcamute", "/-prefs/hardmute") and isinstance(value, (int, float)):
                if address.endswith("dcamute"):
                    self.dca_mutes_enabled = self._bool(value)
                else:
                    self.hard_mutes_enabled = self._bool(value)
                self.received.add(address)
                return True

            if (address.startswith(("/-show/", "/-action/")) or
                    (address.startswith("/-prefs/") and not address.startswith(("/-prefs/rta/", "/-prefs/card/"))
                     and address not in ("/-prefs/dcamute", "/-prefs/hardmute"))):
                if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                    return False
                if isinstance(value, float) and not math.isfinite(value):
                    return False
                self.misc_nodes[address] = value
                self.received.add(address)
                return True

            if len(parts) == 3 and parts[0] == "config" and parts[1] == "mute":
                number = int(parts[2])
                if number not in self.mute_groups:
                    return False
                self.mute_groups[number] = self._bool(value)
                self.received.add(address)
                return True

            if len(parts) >= 4 and parts[0] == "bus" and parts[2] not in ("config", "mix", "grp") and address in self.strip_nodes:
                if not self._valid_strip_node_value(address, value):
                    return False
                self.strip_nodes[address] = value
                self.received.add(address)
                return True

            if len(parts) == 5 and parts[0] == "bus" and parts[2] == "mix":
                number, matrix, field_name = int(parts[1]), int(parts[3]), parts[4]
                if (number not in self.buses or not 1 <= matrix <= 6
                        or field_name not in ("on", "level", "pan", "type", "panFollow")):
                    return False
                if not self._valid_strip_node_value(address, value):
                    return False
                send = self.buses[number].setdefault("matrix_sends", {}).setdefault(
                    matrix, {"on": True, "level": 0.0})
                send[field_name] = int(value) if field_name in ("on", "type", "panFollow") else float(value)
                self.strip_nodes[address] = send[field_name]
                self.received.add(address)
                return True

            if len(parts) == 4 and parts[0] == "bus":
                number = int(parts[1])
                if number not in self.buses:
                    return False
                if parts[2:] == ["config", "name"] and isinstance(value, str) and len(value) <= 12:
                    self.buses[number]["name"] = value
                elif parts[2:] == ["config", "icon"] and self._valid_strip_node_value(address, value):
                    self.buses[number]["icon"] = int(value)
                elif parts[2:] == ["config", "color"] and self._valid_strip_node_value(address, value):
                    self.buses[number]["colour"] = int(value)
                elif parts[2:] == ["mix", "on"] and self._valid_strip_node_value(address, value):
                    self.buses[number]["on"] = self._bool(value)
                elif parts[2:] == ["mix", "fader"] and self._valid_strip_node_value(address, value):
                    self.buses[number]["fader"] = float(value)
                    self.strip_nodes[address] = float(value)
                elif parts[2] == "mix" and parts[3] in ("st", "pan", "mono", "mlevel") and self._valid_strip_node_value(address, value):
                    self.strip_nodes[address] = value
                elif parts[2:] == ["grp", "dca"] and self._valid_strip_node_value(address, value):
                    self.buses[number]["dca_mask"] = int(value)
                elif parts[2:] == ["grp", "mute"] and self._valid_strip_node_value(address, value):
                    self.buses[number]["mute_mask"] = int(value)
                else:
                    return False
                self.received.add(address)
                return True

            if address.startswith(("/main/st/mix/", "/main/m/mix/")) and len(parts) == 5:
                key = "main_st" if address.startswith("/main/st/") else "main_mono"
                matrix = int(parts[3])
                if not 1 <= matrix <= 6 or parts[4] not in ("on", "level"):
                    return False
                send = self.outputs[key]["sends"].setdefault(matrix, {"on": True, "level": 0.0})
                send[parts[4]] = self._bool(value) if parts[4] == "on" else max(0.0, min(1.0, float(value)))
                self.received.add(address)
                return True

            if address.startswith(("/main/st/", "/main/m/")):
                key = "main_st" if address.startswith("/main/st/") else "main_mono"
                if address in self.strip_nodes:
                    if not self._valid_main_node_value(address, value):
                        return False
                    self.strip_nodes[address] = value
                    suffix = address.split("/")[3:]
                    if suffix == ["config", "name"]: pass
                    elif suffix == ["mix", "on"]: self.outputs[key]["on"] = self._bool(value)
                    elif suffix == ["mix", "fader"]: self.outputs[key]["fader"] = float(value)
                    elif suffix == ["mix", "pan"]: self.outputs[key]["pan"] = float(value)
                    elif suffix == ["grp", "dca"]: self.outputs[key]["dca_mask"] = int(value)
                    elif suffix == ["grp", "mute"]: self.outputs[key]["mute_mask"] = int(value)
                    self.received.add(address)
                    return True
                if len(parts) == 5 and parts[2] == "mix":
                    matrix = int(parts[3])
                    if not 1 <= matrix <= 6 or parts[4] not in ("on", "level"):
                        return False
                    send = self.outputs[key]["sends"].setdefault(matrix, {"on": True, "level": 0.0})
                    if parts[4] == "on" and isinstance(value, (int, float)) and int(value) in (0, 1):
                        send["on"] = self._bool(value)
                    elif parts[4] == "level" and isinstance(value, (int, float)) and 0 <= float(value) <= 1:
                        send["level"] = float(value)
                    else:
                        return False
                    self.received.add(address)
                    return True
                return False
        except (ValueError, KeyError, TypeError):
            return False
        return False

    @staticmethod
    def _valid_main_node_value(address, value):
        parts = address.strip("/").split("/")
        if len(parts) < 3 or "/".join(parts[:2]) not in ("main/st", "main/m"):
            return False
        node = "/".join(parts[2:-1])
        field_name = parts[-1]
        schema = MAIN_MONO_NODE_SCHEMA if address.startswith("/main/m/") else MAIN_NODE_SCHEMA
        try:
            spec = schema[node][field_name]
        except KeyError:
            return False
        default, minimum, maximum, step, kind, labels = spec
        if kind == "string":
            return isinstance(value, str) and len(value) <= 12
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if kind in ("int", "enum") and float(value) != int(value):
            return False
        numeric = float(value)
        if minimum is not None and numeric < minimum or maximum is not None and numeric > maximum:
            return False
        if step and minimum is not None and abs((numeric - minimum) / step - round((numeric - minimum) / step)) > 1e-6:
            return False
        return True

    @staticmethod
    def _valid_strip_node_value(address, value):
        parts = address.strip("/").split("/")
        if len(parts) < 4:
            return False
        family, node = parts[0], "/".join(parts[2:-1])
        field_name = parts[-1]
        try:
            spec = STRIP_NODE_SCHEMA[family][node][field_name]
        except KeyError:
            return False
        default, minimum, maximum, step, kind, labels = spec
        if kind == "string":
            return isinstance(value, str) and len(value) <= 12
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if kind in ("int", "enum") and float(value) != int(value):
            return False
        numeric = float(value)
        if minimum is not None and numeric < minimum or maximum is not None and numeric > maximum:
            return False
        if step and minimum is not None and abs((numeric - minimum) / step - round((numeric - minimum) / step)) > 1e-6:
            return False
        return True

    def get(self, address):
        routed = self.routing.get(address)
        if routed is not None:
            return routed
        parts = address.strip("/").split("/")
        try:
            if len(parts) >= 4 and parts[0] in ("ch", "auxin", "fxrtn"):
                collection = {"ch": self.channels, "auxin": self.auxins, "fxrtn": self.fx_returns}[parts[0]]
                channel = collection[int(parts[1])]
                path = "/".join(parts[2:])
                basic = {
                    "config/name": channel.name, "config/color": channel.colour,
                    "config/source": channel.source, "mix/fader": channel.fader,
                    "mix/on": 0 if channel.muted else 1,
                    "mix/st": int(channel.main_st), "mix/mono": int(channel.main_mono),
                    "mix/mlevel": channel.main_mono_level,
                    "grp/dca": channel.dca_mask, "grp/mute": channel.mute_mask,
                }
                if path in basic:
                    return basic[path]
                if len(parts) == 5 and parts[2] == "mix" and parts[3].isdigit() and parts[4] == "type":
                    return channel.send_types.get(int(parts[3]), 4)
                if len(parts) == 5 and parts[2] == "mix" and parts[3].isdigit():
                    send = channel.sends.get(int(parts[3]), {"on": True, "level": 0.0})
                    return send.get(parts[4], self.strip_nodes.get(address))
                return self.strip_nodes.get(address)
                return self.strip_nodes.get(address)
            if len(parts) >= 3 and parts[0] == "fx":
                number = int(parts[1])
                fx = self.fx.get(number)
                if fx is None:
                    return None
                field = parts[2:]
                if field == ["type"]:
                    return fx["type"]
                if field == ["source", "l"]:
                    return fx["source_l"]
                if field == ["source", "r"]:
                    return fx["source_r"]
                if len(field) == 2 and field[0] == "par" and field[1].isdigit():
                    return fx["par"].get(int(field[1]))
                return None
            if parts[:1] == ["-urec"] and len(parts) == 2:
                return self.urec.get(parts[1])
            if len(parts) == 4 and parts[0] == "-urec" and parts[1] == "session" and parts[3] == "name":
                return self.urec_sessions.get(int(parts[2]), "")
            if len(parts) == 4 and parts[0] == "-urec" and parts[1] == "marker" and parts[3] == "time":
                return self.urec_markers.get(int(parts[2]), 0)
            if len(parts) == 3 and parts[:2] == ["-stat", "urec"]:
                return self.urec_status.get(parts[2])
            if len(parts) == 4 and parts[:3] in (["config", "userrout", "out"], ["config", "userrout", "in"]):
                slot_text = parts[3]
                if not slot_text.isdigit() or len(slot_text) != 2:
                    return None
                slots = self.user_rout_out if parts[2] == "out" else self.user_rout_in
                return slots.get(int(slot_text))
            if len(parts) in (4, 5) and parts[:2] == ["config", "userctrl"]:
                bank, section = parts[2], parts[3]
                if bank not in self.user_controls:
                    return None
                if section == "color" and len(parts) == 4:
                    return self.user_controls[bank]["color"]
                if section in ("enc", "btn") and len(parts) == 5 and parts[4].isdigit():
                    return self.user_controls[bank][section].get(int(parts[4]))
            if len(parts) == 3 and parts[:2] == ["config", "tape"]:
                return self.tape_config.get(parts[2])
            if len(parts) == 3 and parts[:2] == ["config", "amixenable"]:
                return self.amix_enable.get(parts[2])
            if len(parts) == 3 and parts[:2] == ["config", "dp48"]:
                return self.dp48_config.get(parts[2])
            if len(parts) == 4 and parts[:2] == ["config", "dp48"] and parts[2] in ("link", "assign", "grpname") and parts[3].isdigit():
                return self.dp48_config[parts[2]].get(int(parts[3]))
            if len(parts) == 3 and parts[:2] == ["config", "osc"]:
                return self.osc_config.get(parts[2])
            if len(parts) == 3 and parts[:2] == ["config", "talk"]:
                return self.talk_config.get(parts[2])
            if len(parts) == 4 and parts[:2] == ["config", "talk"] and parts[2] in ("A", "B"):
                return self.talk_config[parts[2]].get(parts[3])
            if len(parts) == 3 and parts[:2] == ["config", "linkcfg"]:
                return self.link_config.get(parts[2])
            if len(parts) == 3 and parts[:2] == ["config", "mono"]:
                return self.mono_config.get(parts[2])
            if len(parts) == 3 and parts[:2] == ["config", "solo"]:
                return self.solo_config.get(parts[2])
            if len(parts) == 3 and parts[0] == "config" and parts[1] in self.config_links:
                return self.config_links[parts[1]].get(parts[2])
            if address == "/-prefs/rta/visibility":
                return self.preferences["rta/visibility"]
            if address == "/-prefs/rta/gain":
                return self.preferences["rta/gain"]
            if address == "/-prefs/rta/autogain":
                return self.preferences["rta/autogain"]
            if address == "/-prefs/rta/source":
                return self.preferences["rta/source"]
            if address == "/-prefs/rta/pos":
                return self.preferences["rta/pos"]
            if address == "/-prefs/rta/mode":
                return self.preferences["rta/mode"]
            if address in ("/-prefs/rta/options", "/-prefs/rta/option"):
                return self.preferences["rta/options"]
            if address in ("/-prefs/rta/det", "/-prefs/rta/decay", "/-prefs/rta/peakhold"):
                return self.preferences["rta/" + address.rsplit("/", 1)[-1]]
            if address.startswith("/-stat/") and address.rsplit("/", 1)[-1] in self.rta_status:
                return self.rta_status[address.rsplit("/", 1)[-1]]
            if address == "/-stat/keysolo":
                return self.key_solo
            if len(parts) == 3 and parts[:2] == ["-stat", "solosw"] and parts[2].isdigit():
                return self.solo_switches.get(int(parts[2]))
            if len(parts) == 3 and parts[:2] == ["-prefs", "card"]:
                return self.card_preferences.get(parts[2])
            if address.startswith(("/-show/", "/-prefs/", "/-action/")):
                return self.misc_nodes.get(address)
            if address == "/-prefs/dcamute":
                return int(self.dca_mutes_enabled) if self.dca_mutes_enabled is not None else None
            if address == "/-prefs/hardmute":
                return int(self.hard_mutes_enabled) if self.hard_mutes_enabled is not None else None
            if len(parts) >= 4 and parts[0] == "mtx":
                matrix = self.matrices[int(parts[1])]
                if parts[2:] == ["config", "name"]: return matrix["name"]
                if parts[2:] == ["config", "icon"]: return matrix["icon"]
                if parts[2:] == ["config", "color"]: return matrix["colour"]
                if parts[2:] in (["preamp", "invert"], ["config", "preamp", "invert"]):
                    return self.strip_nodes.get("/mtx/%02d/preamp/invert" % int(parts[1]), 0)
                if parts[2:] == ["mix", "on"]: return matrix["on"]
                if parts[2:] == ["mix", "fader"]: return matrix["fader"]
                if parts[2:] == ["grp", "dca"]: return matrix["dca_mask"]
                if parts[2:] == ["grp", "mute"]: return matrix["mute_mask"]
                return self.strip_nodes.get(address)
            if len(parts) >= 4 and parts[0] == "bus" and parts[2] not in ("config", "mix", "grp") and address in self.strip_nodes:
                return self.strip_nodes.get(address)
            if len(parts) == 5 and parts[0] == "bus" and parts[2] == "mix":
                send = self.buses[int(parts[1])].get("matrix_sends", {}).get(
                    int(parts[3]), {"on": True, "level": 0.0})
                return send.get(parts[4], self.strip_nodes.get(address))
            if address.startswith(("/main/st/mix/", "/main/m/mix/")) and len(parts) == 5:
                key = "main_st" if address.startswith("/main/st/") else "main_mono"
                matrix = int(parts[3])
                default_send = {"on": 1, "level": 0.0}
                if matrix % 2:
                    default_send.update({"pan": 0.0, "type": 4, "panFollow": 0})
                return self.outputs[key]["sends"].get(matrix, default_send).get(parts[4])
            if len(parts) == 3 and parts[0] == "headamp" and parts[1].isdigit():
                number = int(parts[1])
                if number not in self.headamps or parts[2] not in ("gain", "phantom"):
                    return None
                return self.headamps[number][parts[2]]
            if len(parts) >= 4 and parts[0] == "outputs" and parts[1] in ("main", "aux", "p16", "aes", "rec"):
                collection = {"main": self.output_main, "aux": self.output_aux, "p16": self.output_p16, "aes": self.output_aes, "rec": self.output_rec}[parts[1]]
                output = collection.get(int(parts[2]))
                if output is None: return None
                field = parts[3:]
                if field == ["src"]: return output["src"]
                if field == ["pos"]: return output["pos"]
                if field == ["invert"] and parts[1] in ("main", "aux", "aes"): return output["invert"]
                if parts[1] == "p16" and field == ["iQ", "group"]: return output["iq_group"]
                if parts[1] == "p16" and field == ["iQ", "speaker"]: return output["iq_speaker"]
                if parts[1] == "main" and field == ["delay", "on"]: return output["delay_on"]
                if parts[1] == "main" and field == ["delay", "time"]: return output["delay_time"]
                return None
            if len(parts) >= 3 and parts[0] == "dca":
                dca = self.dcas.get(int(parts[1]))
                if dca is None:
                    return None
                field = "/".join(parts[2:])
                return {"on": int(dca["on"]), "fader": dca["fader"],
                        "config/name": dca["name"], "config/icon": dca["icon"],
                        "config/color": dca["colour"]}.get(field)
            if len(parts) == 3 and parts[:2] == ["config", "mute"]:
                return int(self.mute_groups[int(parts[2])])
            if len(parts) == 4 and parts[0] == "bus":
                if parts[2:] == ["config", "name"]: return self.buses[int(parts[1])]["name"]
                if parts[2:] == ["config", "icon"]: return self.buses[int(parts[1])]["icon"]
                if parts[2:] == ["config", "color"]: return self.buses[int(parts[1])]["colour"]
                if parts[2:] == ["grp", "dca"]: return self.buses[int(parts[1])]["dca_mask"]
                if parts[2:] == ["grp", "mute"]: return self.buses[int(parts[1])]["mute_mask"]
                if parts[2] == "mix":
                    return self.strip_nodes.get(address, self.buses[int(parts[1])].get(parts[3]))
                return None
            if address.startswith(("/main/st/", "/main/m/")):
                key = "main_st" if address.startswith("/main/st/") else "main_mono"
                if address.endswith("/grp/dca"): return self.outputs[key]["dca_mask"]
                if address.endswith("/grp/mute"): return self.outputs[key]["mute_mask"]
                if address.endswith("/mix/on"): return self.outputs[key]["on"]
                if address.endswith("/mix/fader"): return self.outputs[key]["fader"]
                return self.strip_nodes.get(address)
        except (ValueError, KeyError):
            return None
        return None

    @staticmethod
    def source_label(source):
        if source == 0: return "OFF"
        if 1 <= source <= 32: return "IN%02d" % source
        if 33 <= source <= 38: return "AUX%d" % (source - 32)
        if source == 39: return "USB L"
        if source == 40: return "USB R"
        if 41 <= source <= 48: return "FX%d%s" % ((source - 41) // 2 + 1, "L" if (source - 41) % 2 == 0 else "R")
        if 49 <= source <= 64: return "BUS%02d" % (source - 48)
        return "SRC %d" % source

    def visible_channels(self):
        strips = ([("channel", c) for c in self.channels.values()] +
                  [("aux", c) for c in self.auxins.values()] +
                  [("fx_return", c) for c in self.fx_returns.values()])
        result = []
        for kind, channel in strips:
            if channel.connected and channel.colour != 0:
                item = channel.as_dict()
                item["stripType"] = kind
                result.append(item)
        return result

    def _known(self, address):
        return self.mode == "simulator" or address in self.received

    def _upstream_mutes(self, channel, include_channel_fader=True, include_dca_fader=True,
                        include_channel_mute=True, prefix=None):
        reasons = []
        uncertain = []
        prefix = prefix or "/ch/%02d/" % channel.number
        if not self._known(prefix + "mix/on"):
            uncertain.append("channel_mute_unknown")
        elif channel.muted:
            if include_channel_mute or self.hard_mutes_enabled is True:
                reasons.append("channel_muted")
            elif self.hard_mutes_enabled is None:
                uncertain.append("hard_mute_setting_unknown")
        if include_channel_fader:
            if not self._known(prefix + "mix/fader"):
                uncertain.append("channel_fader_unknown")
            elif channel.fader <= 0.000001:
                reasons.append("channel_fader_zero")
        if not self._known(prefix + "grp/mute"):
            uncertain.append("mute_group_assignments_unknown")
        else:
            for group in range(1, 7):
                if channel.mute_mask & (1 << (group - 1)):
                    address = "/config/mute/%d" % group
                    if not self._known(address):
                        uncertain.append("mute_group_%d_state_unknown" % group)
                    elif self.mute_groups[group]:
                        reasons.append("mute_group_%d" % group)
        if not self._known(prefix + "grp/dca"):
            uncertain.append("dca_assignments_unknown")
        else:
            for dca in range(1, 9):
                if channel.dca_mask & (1 << (dca - 1)):
                    if self.dca_mutes_enabled is not False:
                        if not self._known("/dca/%d/on" % dca):
                            uncertain.append("dca_%d_state_unknown" % dca)
                        elif not self.dcas[dca]["on"]:
                            if self.dca_mutes_enabled is True:
                                reasons.append("dca_%d_muted" % dca)
                            else:
                                uncertain.append("dca_mute_setting_unknown")
                    if include_dca_fader:
                        if not self._known("/dca/%d/fader" % dca):
                            uncertain.append("dca_%d_fader_unknown" % dca)
                        elif self.dcas[dca]["fader"] <= 0.000001:
                            reasons.append("dca_%d_fader_zero" % dca)
        return reasons, uncertain

    def _destination_mutes(self, prefix, dca_mask, mute_mask):
        reasons = []
        uncertain = []
        if not self._known(prefix + "grp/mute"):
            uncertain.append("output_mute_group_assignments_unknown")
        else:
            for group in range(1, 7):
                if mute_mask & (1 << (group - 1)):
                    address = "/config/mute/%d" % group
                    if not self._known(address):
                        uncertain.append("mute_group_%d_state_unknown" % group)
                    elif self.mute_groups[group]:
                        reasons.append("output_mute_group_%d" % group)
        if not self._known(prefix + "grp/dca"):
            uncertain.append("output_dca_assignments_unknown")
        else:
            for dca in range(1, 9):
                if dca_mask & (1 << (dca - 1)):
                    if self.dca_mutes_enabled is not False:
                        if not self._known("/dca/%d/on" % dca):
                            uncertain.append("dca_%d_state_unknown" % dca)
                        elif not self.dcas[dca]["on"]:
                            if self.dca_mutes_enabled is True:
                                reasons.append("dca_%d_muted" % dca)
                            else:
                                uncertain.append("dca_mute_setting_unknown")
                    if not self._known("/dca/%d/fader" % dca):
                        uncertain.append("dca_%d_fader_unknown" % dca)
                    elif self.dcas[dca]["fader"] <= 0.000001:
                        reasons.append("dca_%d_fader_zero" % dca)
        return reasons, uncertain

    @staticmethod
    def _cell(reasons, uncertain=None, send_on=True, send_level=1.0, output_on=True, output_fader=1.0):
        causes = list(reasons)
        uncertain = list(uncertain or [])
        if not send_on: causes.append("send_off")
        if send_level <= 0.000001: causes.append("send_level_zero")
        if not output_on: causes.append("output_muted")
        if output_fader <= 0.000001: causes.append("output_fader_zero")
        return {"muted": bool(causes), "uncertain": bool(uncertain and not causes),
                "reasons": causes + uncertain, "send_on": send_on, "send_level": send_level}

    def matrix_input_matrix(self):
        """Trace each bus/Main output into Matrix 1–6, including both send and output mutes."""
        sources = []
        for number, bus in self.buses.items():
            sources.append({
                "id": "bus_%02d" % number, "label": bus.get("name") or "Bus %02d" % number,
                "prefix": "/bus/%02d/" % number, "on": bus["on"], "fader": bus["fader"],
                "dca_mask": bus["dca_mask"], "mute_mask": bus["mute_mask"],
                "sends": bus.get("matrix_sends", {}),
            })
        for key, label, prefix in (
            ("main_st", "Main L/R", "/main/st/"),
            ("main_mono", "Mono/C", "/main/m/"),
        ):
            output = self.outputs[key]
            sources.append({
                "id": key, "label": label, "prefix": prefix,
                "on": output["on"], "fader": output["fader"],
                "dca_mask": output["dca_mask"], "mute_mask": output["mute_mask"],
                "sends": output["sends"],
            })
        destinations = [
            {"id": "mtx_%02d" % n, "label": self.matrices[n]["name"], "kind": "matrix"}
            for n in range(1, 7)
        ]
        rows = []
        for source in sources:
            cells = {}
            for number in range(1, 7):
                matrix = self.matrices[number]
                send = source["sends"].get(number, {"on": True, "level": 0.0})
                send_prefix = source["prefix"] + "mix/%02d/" % number
                matrix_prefix = "/mtx/%02d/" % number
                reasons, uncertain = [], []
                for suffix, reason in (("mix/on", "source_muted"), ("mix/fader", "source_fader_zero")):
                    if not self._known(source["prefix"] + suffix):
                        uncertain.append("matrix_source_state_unknown")
                    elif suffix == "mix/on" and not source["on"]:
                        reasons.append(reason)
                    elif suffix == "mix/fader" and source["fader"] <= 0.000001:
                        reasons.append(reason)
                if not self._known(source["prefix"] + "grp/dca") or not self._known(source["prefix"] + "grp/mute"):
                    uncertain.append("matrix_source_groups_unknown")
                else:
                    group_reasons, group_uncertain = self._destination_mutes(
                        source["prefix"], source["dca_mask"], source["mute_mask"])
                    reasons.extend(group_reasons)
                    uncertain.extend(group_uncertain)
                if not self._known(send_prefix + "on"):
                    uncertain.append("matrix_send_switch_unknown")
                if not self._known(send_prefix + "level"):
                    uncertain.append("matrix_send_level_unknown")
                if not self._known(matrix_prefix + "mix/on"):
                    uncertain.append("matrix_output_mute_unknown")
                if not self._known(matrix_prefix + "mix/fader"):
                    uncertain.append("matrix_output_fader_unknown")
                matrix_reasons, matrix_uncertain = self._destination_mutes(
                    matrix_prefix, matrix["dca_mask"], matrix["mute_mask"])
                reasons.extend(matrix_reasons)
                uncertain.extend(matrix_uncertain)
                cells["mtx_%02d" % number] = self._cell(
                    reasons, uncertain,
                    send["on"] if self._known(send_prefix + "on") else True,
                    send["level"] if self._known(send_prefix + "level") else 1.0,
                    matrix["on"] if self._known(matrix_prefix + "mix/on") else True,
                    matrix["fader"] if self._known(matrix_prefix + "mix/fader") else 1.0,
                )
            rows.append({"id": source["id"], "name": source["label"], "cells": cells})
        return {"destinations": destinations, "sources": rows}

    def output_matrix(self):
        """Return per-channel signal availability for Main L/R, Mono/C and buses 1–16."""
        destinations = [
            {"id": "main_st", "label": "Main L/R", "kind": "main"},
            {"id": "main_mono", "label": "Mono/C", "kind": "main"},
        ] + [{"id": "bus_%02d" % n, "label": "Bus %02d" % n, "kind": "bus"} for n in range(1, 17)]
        rows = []
        sources = [("/ch/%02d/" % c.number, c) for c in self.channels.values()]
        sources += [("/auxin/%02d/" % c.number, c) for c in self.auxins.values()]
        sources += [("/fxrtn/%02d/" % c.number, c) for c in self.fx_returns.values()]
        for prefix, channel in sources:
            if not channel.connected or channel.colour == 0:
                continue
            cells = {}
            for destination in destinations:
                ident = destination["id"]
                if ident in ("main_st", "main_mono"):
                    suffix = "mix/st" if ident == "main_st" else "mix/mono"
                    reasons, uncertain = self._upstream_mutes(channel, prefix=prefix)
                    if not self._known(prefix + suffix):
                        uncertain.append("main_send_state_unknown")
                    if ident == "main_mono" and not self._known(prefix + "mix/mlevel"):
                        uncertain.append("main_mono_send_level_unknown")
                    if not self._known("/%s/mix/on" % ("main/st" if ident == "main_st" else "main/m")):
                        uncertain.append("output_mute_state_unknown")
                    if not self._known("/%s/mix/fader" % ("main/st" if ident == "main_st" else "main/m")):
                        uncertain.append("output_fader_state_unknown")
                    send_on = getattr(channel, "main_st" if ident == "main_st" else "main_mono") if self._known(prefix + suffix) else True
                    output = self.outputs[ident]
                    output_prefix = "/main/st/" if ident == "main_st" else "/main/m/"
                    destination_reasons, destination_uncertain = self._destination_mutes(
                        output_prefix, output["dca_mask"], output["mute_mask"])
                    reasons.extend(destination_reasons)
                    uncertain.extend(destination_uncertain)
                    output_on = output["on"] if self._known(output_prefix + "mix/on") else True
                    output_fader = output["fader"] if self._known(output_prefix + "mix/fader") else 1.0
                    send_level = channel.main_mono_level if ident == "main_mono" else 1.0
                    cells[ident] = self._cell(reasons, uncertain, send_on, send_level, output_on, output_fader)
                else:
                    bus = int(ident[-2:])
                    send = channel.sends.get(bus, {"on": True, "level": 0.0})
                    type_bus = bus if bus % 2 else bus - 1
                    type_address = prefix + "mix/%02d/type" % type_bus
                    type_known = self._known(type_address)
                    send_type = channel.send_types.get(type_bus, 4) if type_known else 3
                    reasons, uncertain = self._upstream_mutes(
                        channel, include_channel_fader=(send_type in (4, 5)),
                        include_dca_fader=(send_type in (4, 5)),
                        include_channel_mute=(send_type in (4, 5)), prefix=prefix)
                    if not type_known:
                        uncertain.append("send_tap_point_unknown")
                    send_prefix = prefix + "mix/%02d/" % bus
                    on_known = self._known(send_prefix + "on")
                    level_known = self._known(send_prefix + "level")
                    if not on_known: uncertain.append("send_switch_state_unknown")
                    if not level_known: uncertain.append("send_level_state_unknown")
                    output_prefix = "/bus/%02d/mix/" % bus
                    output_on_known = self._known(output_prefix + "on")
                    output_fader_known = self._known(output_prefix + "fader")
                    if not output_on_known: uncertain.append("output_mute_state_unknown")
                    if not output_fader_known: uncertain.append("output_fader_state_unknown")
                    destination_prefix = "/bus/%02d/" % bus
                    destination_reasons, destination_uncertain = self._destination_mutes(
                        destination_prefix, self.buses[bus]["dca_mask"], self.buses[bus]["mute_mask"])
                    reasons.extend(destination_reasons)
                    uncertain.extend(destination_uncertain)
                    cells[ident] = self._cell(
                        reasons, uncertain,
                        send["on"] if on_known else True,
                        send["level"] if level_known else 1.0,
                        self.buses[bus]["on"] if output_on_known else True,
                        self.buses[bus]["fader"] if output_fader_known else 1.0)
            rows.append({"number": channel.number, "name": channel.name,
                         "source": "FX RETURN" if prefix.startswith("/fxrtn/") else self.source_label(channel.source),
                         "strip_type": "fx_return" if prefix.startswith("/fxrtn/") else "aux" if prefix.startswith("/auxin/") else "channel",
                         "cells": cells})
        return {"destinations": destinations, "channels": rows,
                "dcas": list(self.dcas.values()),
                "mute_groups": [{"number": n, "muted": active} for n, active in self.mute_groups.items()],
                "dca_mutes_enabled": self.dca_mutes_enabled,
                "hard_mutes_enabled": self.hard_mutes_enabled}

