"""Read-only inventory of M32 patchbay, FX and monitor routing parameters.

Values are retained exactly as returned by OSC. Unknown enum values remain visible
as raw values rather than being guessed.
"""
from dataclasses import dataclass

INPUT_BANKS = ("AN 1-8", "AN 9-16", "AN 17-24", "AN 25-32",
               "AES50-A 1-8", "AES50-A 9-16", "AES50-A 17-24", "AES50-A 25-32",
               "AES50-A 33-40", "AES50-A 41-48", "AES50-B 1-8", "AES50-B 9-16",
               "AES50-B 17-24", "AES50-B 25-32", "AES50-B 33-40", "AES50-B 41-48",
               "Card 1-8", "Card 9-16", "Card 17-24", "Card 25-32",
               "USB 1-8", "USB 9-16", "USB 17-24", "USB 25-32")
AUX_INPUT_BANKS = ("Aux 1-6", "Local 1-2", "Local 1-4", "Local 1-6",
                   "AES50-A 1-2", "AES50-A 1-4", "AES50-A 1-6",
                   "AES50-B 1-2", "AES50-B 1-4", "AES50-B 1-6",
                   "Card 1-2", "Card 1-4", "Card 1-6",
                   "USB 1-2", "USB 1-4", "USB 1-6")
OUTPUT_BANKS = (
    "Local 1-8", "Local 9-16", "Local 17-24", "Local 25-32",
    "AES50-A 1-8", "AES50-A 9-16", "AES50-A 17-24", "AES50-A 25-32", "AES50-A 33-40", "AES50-A 41-48",
    "AES50-B 1-8", "AES50-B 9-16", "AES50-B 17-24", "AES50-B 25-32", "AES50-B 33-40", "AES50-B 41-48",
    "Card 1-8", "Card 9-16", "Card 17-24", "Card 25-32",
    "Out 1-8", "Out 9-16", "P16 1-8", "P16 9-16", "Aux 1-6 / Monitor", "Aux inputs 1-6 / Talkback",
    "Ultranet 1-8", "Ultranet 9-16", "Ultranet 17-24", "Ultranet 25-32",
    "Ultranet 33-40", "Ultranet 41-48", "USB 1-8", "USB 9-16", "USB 17-24", "USB 25-32"
)
OUTPUT_BLOCKS = ("1-4", "5-8", "9-12", "13-16")
ROUTING_PATHS = {
    "/config/routing/IN/1-8": ("Input patch", INPUT_BANKS),
    "/config/routing/IN/9-16": ("Input patch", INPUT_BANKS),
    "/config/routing/IN/17-24": ("Input patch", INPUT_BANKS),
    "/config/routing/IN/25-32": ("Input patch", INPUT_BANKS),
    "/config/routing/IN/AUX": ("Aux input patch", AUX_INPUT_BANKS),
}
for family in ("AES50A", "AES50B", "CARD"):
    for bank in ("1-8", "9-16", "17-24", "25-32", "33-40", "41-48"):
        if family == "CARD" and bank in ("33-40", "41-48"):
            continue
        ROUTING_PATHS[f"/config/routing/{family}/{bank}"] = (family + " output patch", OUTPUT_BANKS)
for bank in OUTPUT_BLOCKS:
    ROUTING_PATHS[f"/config/routing/OUT/{bank}"] = ("Output patch " + bank, OUTPUT_BANKS)
for bank in ("1-8", "9-16", "17-24", "25-32"):
    ROUTING_PATHS[f"/config/routing/PLAY/{bank}"] = ("Playback patch", INPUT_BANKS)
ROUTING_PATHS["/config/routing/PLAY/AUX"] = ("Playback Aux patch", AUX_INPUT_BANKS)
ROUTING_PATHS["/config/routing/outswitch"] = ("Routing mode", ("Record", "Playback"))
ROUTING_PATHS["/config/routing/routswitch"] = ("Routing mode", ("Record", "Playback"))

def _enum_label(value, choices):
    try:
        index = int(value)
        return choices[index] if 0 <= index < len(choices) else f"Unknown enum ({value})"
    except (TypeError, ValueError):
        return str(value)

class RoutingState:
    """Raw, freshness-aware routing snapshot for patchbay and auxiliary subsystems."""
    def __init__(self):
        self.values = {}

    def update(self, address, value):
        if address.startswith("/config/routing/") or address.startswith("/outputs/") or address.startswith("/config/userrout/") or address.startswith("/fx/") or address.startswith("/config/solo/") or address.startswith("/config/talk/") or address.startswith("/ch/") and "/insert" in address:
            self.values[address] = value
            return True
        return False

    def get(self, address):
        return self.values.get(address)

    def snapshot(self):
        sections = {}
        for address, (section, choices) in ROUTING_PATHS.items():
            if address not in self.values:
                item = {"address": address, "label": address.rsplit("/", 1)[-1], "known": False, "value": None, "display": "Not received"}
            else:
                value = self.values[address]
                item = {"address": address, "label": address.rsplit("/", 1)[-1], "known": True,
                        "value": value, "display": _enum_label(value, choices)}
            sections.setdefault(section, []).append(item)
        outputs = []
        for family, count in (("main", 16), ("aux", 6), ("p16", 16)):
            for number in range(1, count + 1):
                address = f"/outputs/{family}/{number:02d}"
                value = self.values.get(address)
                outputs.append({"address": address, "label": f"{family.upper()} {number:02d}",
                                "known": address in self.values, "value": value,
                                "display": str(value) if address in self.values else "Not received"})
        fx = []
        for number in range(1, 9):
            for suffix in ("type", "source"):
                address = f"/fx/{number}/{suffix}"
                fx.append({"address": address, "label": f"FX {number} {suffix}",
                           "known": address in self.values, "value": self.values.get(address),
                           "display": str(self.values[address]) if address in self.values else "Not received"})
        special = []
        for address, value in sorted(self.values.items()):
            if address.startswith(("/config/solo/", "/config/talk/", "/config/userrout/")) or "/insert" in address:
                special.append({"address": address, "value": value})
        total = len(ROUTING_PATHS) + len(outputs) + len(fx)
        known = sum(1 for a in ROUTING_PATHS if a in self.values) + sum(1 for x in outputs if x["known"]) + sum(1 for x in fx if x["known"])
        return {"sections": [{"name": name, "items": items} for name, items in sections.items()],
                "outputs": outputs, "effects": fx, "special": special,
                "known": known, "total": total, "complete": known == total}
