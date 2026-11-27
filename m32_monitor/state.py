"""Shared console state and effective mute-path calculation."""
from dataclasses import asdict, dataclass, field
import struct
import time
from m32_monitor.routing import RoutingState


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
        self.key_solo = 0
        self.solo_switches = {number: 0 for number in range(1, 81)}
        self.card_preferences = {name: 0 for name in ("UFifc", "UFmode", "USBmode", "ADATwc", "ADATsync", "MADImode", "MADIin", "MADIout", "MADIsrc", "URECtracks", "URECplayb", "URECrout", "URECsdsel")}
        self.received = set()
        self.last_seen = time.monotonic()
        self.auxins = {n: ChannelState(n, "AUX %02d" % n, 0.72, False, 1, 32 + n, False) for n in range(1, 9)}
        self.fx_returns = {n: ChannelState(n, "FX RTN %02d" % n, 0.72, False, 1, 0, False) for n in range(1, 9)}
        self.dcas = {
            n: {"number": n, "name": "DCA %d" % n, "on": True, "fader": 0.75}
            for n in range(1, 9)
        }
        self.mute_groups = {n: False for n in range(1, 7)}
        self.dca_mutes_enabled = None
        self.hard_mutes_enabled = None
        self.buses = {
            n: {"number": n, "name": "Bus %02d" % n, "on": True, "fader": 0.75, "dca_mask": 0, "mute_mask": 0}
            for n in range(1, 17)
        }
        self.outputs = {
            "main_st": {"on": True, "fader": 0.75, "dca_mask": 0, "mute_mask": 0, "sends": {}},
            "main_mono": {"on": True, "fader": 0.75, "dca_mask": 0, "mute_mask": 0, "sends": {}},
        }
        self.matrices = {n: {"number": n, "name": "Matrix %02d" % n, "on": True, "fader": 0.75,
                             "dca_mask": 0, "mute_mask": 0} for n in range(1, 7)}

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
        if self.routing.update(address, value):
            self.received.add(address)
            return True
        parts = address.strip("/").split("/")
        try:
            if len(parts) >= 4 and parts[0] in ("ch", "auxin", "fxrtn"):
                collection = {"ch": self.channels, "auxin": self.auxins, "fxrtn": self.fx_returns}[parts[0]]
                channel = collection[int(parts[1])]
                path = "/".join(parts[2:])
                if path == "config/name" and isinstance(value, str):
                    channel.name = value
                elif path == "config/color" and isinstance(value, (int, float)):
                    channel.colour = int(value)
                elif path == "config/source" and isinstance(value, (int, float)) and parts[0] != "fxrtn":
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
                    else:
                        return False
                else:
                    return False
                if parts[0] == "fxrtn" and path == "config/color":
                    channel.connected = channel.colour != 0
                self.received.add(address)
                return True

            if len(parts) == 3 and parts[0] == "dca":
                number = int(parts[1])
                if number not in self.dcas:
                    return False
                if parts[2] == "on":
                    self.dcas[number]["on"] = self._bool(value)
                elif parts[2] == "fader":
                    self.dcas[number]["fader"] = max(0.0, min(1.0, float(value)))
                elif parts[2] == "config/name" and isinstance(value, str):
                    self.dcas[number]["name"] = value
                else:
                    return False
                self.received.add(address)
                return True

            if len(parts) == 4 and parts[0] == "mtx":
                number = int(parts[1])
                if number not in self.matrices:
                    return False
                if parts[2:] == ["mix", "on"]:
                    self.matrices[number]["on"] = self._bool(value)
                elif parts[2:] == ["mix", "fader"]:
                    self.matrices[number]["fader"] = max(0.0, min(1.0, float(value)))
                elif parts[2:] == ["grp", "dca"]:
                    self.matrices[number]["dca_mask"] = int(value) & 255
                elif parts[2:] == ["grp", "mute"]:
                    self.matrices[number]["mute_mask"] = int(value) & 63
                elif parts[2:] == ["config", "name"] and isinstance(value, str):
                    self.matrices[number]["name"] = value
                else:
                    return False
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

            if len(parts) == 3 and parts[0] == "config" and parts[1] == "mute":
                number = int(parts[2])
                if number not in self.mute_groups:
                    return False
                self.mute_groups[number] = self._bool(value)
                self.received.add(address)
                return True

            if len(parts) == 5 and parts[0] == "bus" and parts[2] == "mix":
                number, matrix = int(parts[1]), int(parts[3])
                if number not in self.buses or not 1 <= matrix <= 6 or parts[4] not in ("on", "level"):
                    return False
                send = self.buses[number].setdefault("matrix_sends", {}).setdefault(matrix, {"on": True, "level": 0.0})
                send[parts[4]] = self._bool(value) if parts[4] == "on" else max(0.0, min(1.0, float(value)))
                self.received.add(address)
                return True

            if len(parts) == 4 and parts[0] == "bus":
                number = int(parts[1])
                if number not in self.buses:
                    return False
                if parts[2:] == ["config", "name"] and isinstance(value, str):
                    self.buses[number]["name"] = value
                elif parts[2:] == ["mix", "on"]:
                    self.buses[number]["on"] = self._bool(value)
                elif parts[2:] == ["mix", "fader"]:
                    self.buses[number]["fader"] = max(0.0, min(1.0, float(value)))
                elif parts[2:] == ["grp", "dca"]:
                    self.buses[number]["dca_mask"] = int(value) & 255
                elif parts[2:] == ["grp", "mute"]:
                    self.buses[number]["mute_mask"] = int(value) & 63
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
                if address.endswith("/mix/on"):
                    self.outputs[key]["on"] = self._bool(value)
                elif address.endswith("/mix/fader"):
                    self.outputs[key]["fader"] = max(0.0, min(1.0, float(value)))
                elif address.endswith("/grp/dca"):
                    self.outputs[key]["dca_mask"] = int(value) & 255
                elif address.endswith("/grp/mute"):
                    self.outputs[key]["mute_mask"] = int(value) & 63
                else:
                    return False
                self.received.add(address)
                return True
        except (ValueError, KeyError, TypeError):
            return False
        return False

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
                    return send.get(parts[4])
            if parts[:1] == ["-urec"] and len(parts) == 2:
                return self.urec.get(parts[1])
            if len(parts) == 4 and parts[0] == "-urec" and parts[1] == "session" and parts[3] == "name":
                return self.urec_sessions.get(int(parts[2]), "")
            if len(parts) == 4 and parts[0] == "-urec" and parts[1] == "marker" and parts[3] == "time":
                return self.urec_markers.get(int(parts[2]), 0)
            if len(parts) == 3 and parts[:2] == ["-stat", "urec"]:
                return self.urec_status.get(parts[2])
            if len(parts) == 3 and parts[:2] == ["config", "linkcfg"]:
                return self.link_config.get(parts[2])
            if len(parts) == 3 and parts[:2] == ["config", "mono"]:
                return self.mono_config.get(parts[2])
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
            if address == "/-prefs/dcamute":
                return int(self.dca_mutes_enabled) if self.dca_mutes_enabled is not None else None
            if address == "/-prefs/hardmute":
                return int(self.hard_mutes_enabled) if self.hard_mutes_enabled is not None else None
            if len(parts) == 4 and parts[0] == "mtx":
                matrix = self.matrices[int(parts[1])]
                if parts[2:] == ["mix", "on"]: return matrix["on"]
                if parts[2:] == ["mix", "fader"]: return matrix["fader"]
                if parts[2:] == ["grp", "dca"]: return matrix["dca_mask"]
                if parts[2:] == ["grp", "mute"]: return matrix["mute_mask"]
                if parts[2:] == ["config", "name"]: return matrix["name"]
            if len(parts) == 5 and parts[0] == "bus" and parts[2] == "mix":
                return self.buses[int(parts[1])].get("matrix_sends", {}).get(int(parts[3]), {"on": True, "level": 0.0}).get(parts[4])
            if address.startswith(("/main/st/mix/", "/main/m/mix/")) and len(parts) == 5:
                key = "main_st" if address.startswith("/main/st/") else "main_mono"
                return self.outputs[key]["sends"].get(int(parts[3]), {"on": True, "level": 0.0}).get(parts[4])
            if len(parts) == 3 and parts[0] == "dca":
                dca = self.dcas[int(parts[1])]
                return dca.get(parts[2])
            if len(parts) == 3 and parts[:2] == ["config", "mute"]:
                return int(self.mute_groups[int(parts[2])])
            if len(parts) == 4 and parts[0] == "bus":
                if parts[2:] == ["config", "name"]: return self.buses[int(parts[1])]["name"]
                if parts[2:] == ["grp", "dca"]: return self.buses[int(parts[1])]["dca_mask"]
                if parts[2:] == ["grp", "mute"]: return self.buses[int(parts[1])]["mute_mask"]
                return self.buses[int(parts[1])].get(parts[3]) if parts[2] == "mix" else None
            if address.startswith(("/main/st/", "/main/m/")):
                key = "main_st" if address.startswith("/main/st/") else "main_mono"
                if address.endswith("/grp/dca"): return self.outputs[key]["dca_mask"]
                if address.endswith("/grp/mute"): return self.outputs[key]["mute_mask"]
                if address.endswith("/mix/on"): return self.outputs[key]["on"]
                if address.endswith("/mix/fader"): return self.outputs[key]["fader"]
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

