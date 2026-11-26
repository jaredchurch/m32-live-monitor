"""Shared console state and effective mute-path calculation."""
from dataclasses import asdict, dataclass, field
import time


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
        self.last_seen = time.monotonic()
        self.dcas = {
            n: {"number": n, "name": "DCA %d" % n, "on": True, "fader": 0.75}
            for n in range(1, 9)
        }
        self.mute_groups = {n: False for n in range(1, 7)}
        self.dca_mutes_enabled = None
        self.hard_mutes_enabled = None
        self.buses = {
            n: {"number": n, "on": True, "fader": 0.75}
            for n in range(1, 17)
        }
        self.outputs = {
            "main_st": {"on": True, "fader": 0.75},
            "main_mono": {"on": True, "fader": 0.75},
        }

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

    def update(self, address, value):
        parts = address.strip("/").split("/")
        try:
            if len(parts) >= 4 and parts[0] == "ch":
                channel = self.channels[int(parts[1])]
                path = "/".join(parts[2:])
                if path == "config/name" and isinstance(value, str):
                    channel.name = value
                elif path == "config/color" and isinstance(value, (int, float)):
                    channel.colour = int(value)
                elif path == "config/source" and isinstance(value, (int, float)):
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
                return True

            if address in ("/-prefs/dcamute", "/-prefs/hardmute") and isinstance(value, (int, float)):
                if address.endswith("dcamute"):
                    self.dca_mutes_enabled = self._bool(value)
                else:
                    self.hard_mutes_enabled = self._bool(value)
                return True

            if len(parts) == 3 and parts[0] == "config" and parts[1] == "mute":
                number = int(parts[2])
                if number not in self.mute_groups:
                    return False
                self.mute_groups[number] = self._bool(value)
                return True

            if len(parts) == 4 and parts[0] == "bus" and parts[2:] in (["mix", "on"], ["mix", "fader"]):
                number = int(parts[1])
                if number not in self.buses:
                    return False
                key = "on" if parts[3] == "on" else "fader"
                self.buses[number][key] = self._bool(value) if key == "on" else max(0.0, min(1.0, float(value)))
                return True

            if address == "/-prefs/dcamute":
                return int(self.dca_mutes_enabled) if self.dca_mutes_enabled is not None else None
            if address == "/-prefs/hardmute":
                return int(self.hard_mutes_enabled) if self.hard_mutes_enabled is not None else None
            if address in ("/main/st/mix/on", "/main/m/mix/on",
                           "/main/st/mix/fader", "/main/m/mix/fader"):
                key = "main_st" if "/st/" in address else "main_mono"
                field_name = "on" if address.endswith("/on") else "fader"
                self.outputs[key][field_name] = self._bool(value) if field_name == "on" else max(0.0, min(1.0, float(value)))
                return True
        except (ValueError, KeyError, TypeError):
            return False
        return False

    def get(self, address):
        parts = address.strip("/").split("/")
        try:
            if len(parts) >= 4 and parts[0] == "ch":
                channel = self.channels[int(parts[1])]
                path = "/".join(parts[2:])
                basic = {
                    "config/name": channel.name, "config/color": channel.colour,
                    "config/source": channel.source, "mix/fader": channel.fader,
                    "mix/on": 0 if channel.muted else 1,
                    "mix/st": int(channel.main_st), "mix/mono": int(channel.main_mono),
                    "grp/dca": channel.dca_mask, "grp/mute": channel.mute_mask,
                }
                if path in basic:
                    return basic[path]
                if len(parts) == 5 and parts[2] == "mix" and parts[3].isdigit() and parts[4] == "type":
                    return channel.send_types.get(int(parts[3]), 4)
                if len(parts) == 5 and parts[2] == "mix" and parts[3].isdigit():
                    send = channel.sends.get(int(parts[3]), {"on": True, "level": 0.0})
                    return send.get(parts[4])
            if address == "/-prefs/dcamute":
                return int(self.dca_mutes_enabled) if self.dca_mutes_enabled is not None else None
            if len(parts) == 3 and parts[0] == "dca":
                dca = self.dcas[int(parts[1])]
                return dca.get(parts[2])
            if len(parts) == 3 and parts[:2] == ["config", "mute"]:
                return int(self.mute_groups[int(parts[2])])
            if len(parts) == 4 and parts[0] == "bus":
                return self.buses[int(parts[1])].get(parts[3]) if parts[2] == "mix" else None
            if address in ("/main/st/mix/on", "/main/m/mix/on",
                           "/main/st/mix/fader", "/main/m/mix/fader"):
                key = "main_st" if "/st/" in address else "main_mono"
                return self.outputs[key]["on" if address.endswith("/on") else "fader"]
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
        return [c.as_dict() for c in self.channels.values() if c.connected and c.colour != 0]

    def _upstream_mutes(self, channel, include_channel_fader=True, include_dca_fader=True, include_channel_mute=True):
        reasons = []
        uncertain = []
        if channel.muted:
            if include_channel_mute or self.hard_mutes_enabled is True:
                reasons.append("channel_muted")
            elif self.hard_mutes_enabled is None:
                uncertain.append("hard_mute_setting_unknown")
        if include_channel_fader and channel.fader <= 0.000001:
            reasons.append("channel_fader_zero")
        for group in range(1, 7):
            if channel.mute_mask & (1 << (group - 1)) and self.mute_groups[group]:
                reasons.append("mute_group_%d" % group)
        for dca in range(1, 9):
            if channel.dca_mask & (1 << (dca - 1)):
                if not self.dcas[dca]["on"]:
                    if self.dca_mutes_enabled is True:
                        reasons.append("dca_%d_muted" % dca)
                    elif self.dca_mutes_enabled is None:
                        uncertain.append("dca_mute_setting_unknown")
                if include_dca_fader and self.dcas[dca]["fader"] <= 0.000001:
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

    def output_matrix(self):
        """Return per-channel signal availability for Main L/R, Mono/C and buses 1–16."""
        destinations = [
            {"id": "main_st", "label": "Main L/R", "kind": "main"},
            {"id": "main_mono", "label": "Mono/C", "kind": "main"},
        ] + [{"id": "bus_%02d" % n, "label": "Bus %02d" % n, "kind": "bus"} for n in range(1, 17)]
        rows = []
        for channel in self.channels.values():
            if not channel.connected or channel.colour == 0:
                continue
            upstream, upstream_uncertain = self._upstream_mutes(channel)
            cells = {}
            for destination in destinations:
                ident = destination["id"]
                if ident == "main_st":
                    cells[ident] = self._cell(upstream, upstream_uncertain, channel.main_st, channel.fader,
                        self.outputs[ident]["on"], self.outputs[ident]["fader"])
                elif ident == "main_mono":
                    cells[ident] = self._cell(upstream, upstream_uncertain, channel.main_mono, channel.fader,
                        self.outputs[ident]["on"], self.outputs[ident]["fader"])
                else:
                    bus = int(ident[-2:])
                    send = channel.sends.get(bus, {"on": True, "level": 0.0})
                    send_type = channel.send_types.get(bus if bus % 2 else bus - 1, 4)
                    bus_reasons, bus_uncertain = self._upstream_mutes(
                        channel, include_channel_fader=(send_type in (4, 5)),
                        include_dca_fader=(send_type in (4, 5)),
                        include_channel_mute=(send_type in (4, 5)))
                    cells[ident] = self._cell(bus_reasons, bus_uncertain, send["on"], send["level"],
                        self.buses[bus]["on"], self.buses[bus]["fader"])
            rows.append({"number": channel.number, "name": channel.name,
                         "source": self.source_label(channel.source), "cells": cells})
        return {"destinations": destinations, "channels": rows,
                "dcas": list(self.dcas.values()),
                "mute_groups": [{"number": n, "muted": active} for n, active in self.mute_groups.items()],
                "dca_mutes_enabled": self.dca_mutes_enabled,\n                "hard_mutes_enabled": self.hard_mutes_enabled}
