"""Read-only inventory of M32 patchbay, FX and monitor routing parameters.

Values are retained exactly as returned by OSC. Unknown enum values remain visible
as raw values rather than being guessed.
"""
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
OUTPUT_SOURCES = ("OFF", "Main L", "Main R", "Mono/C") + tuple("Mix Bus %02d" % n for n in range(1, 17)) + tuple("Matrix %d" % n for n in range(1, 7)) + tuple("Direct Out CH %02d" % n for n in range(1, 33)) + tuple("Direct Out Aux %d" % n for n in range(1, 9)) + tuple("Direct Out FX %d%s" % (n, side) for n in range(1, 5) for side in ("L", "R")) + ("Monitor L", "Monitor R", "Talkback")
OUTPUT_TAPS = ("IN/LC", "IN/LC + Mute", "Pre EQ", "Pre EQ + Mute", "Post EQ", "Post EQ + Mute", "Pre Fader", "Pre Fader + Mute", "Post Fader")

# Stereo-link addresses are retained in the routing inventory only when they
# identify a real adjacent pair on the console.
CONFIG_LINK_ADDRESSES = {
    f"/config/{family}/{n}-{n+1}"
    for family, limit in (("chlink", 32), ("auxlink", 8), ("fxlink", 8),
                          ("buslink", 16), ("mtxlink", 6))
    for n in range(1, limit, 2)
}
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
OUT_PATCH_CHOICES = {
    "1-4": ("Local 1-4","Local 9-12","Local 17-20","Local 25-28",
            "AES50-A 1-4","AES50-A 9-12","AES50-A 17-20","AES50-A 25-28","AES50-A 33-36","AES50-A 41-44",
            "AES50-B 1-4","AES50-B 9-12","AES50-B 17-20","AES50-B 25-28","AES50-B 33-36","AES50-B 41-44",
            "Card 1-4","Card 9-12","Card 17-20","Card 25-28","Out 1-4","Out 9-12","P16 1-4","P16 9-12",
            "Aux / Control Room","Aux / Talkback","Ultranet 1-4","Ultranet 9-12","Ultranet 17-20","Ultranet 25-28",
            "Ultranet 33-36","Ultranet 41-44","USB 1-4","USB 9-12","USB 17-20","USB 25-28"),
    "5-8": ("Local 5-8","Local 13-16","Local 21-24","Local 29-32",
            "AES50-A 5-8","AES50-A 13-16","AES50-A 21-24","AES50-A 29-32","AES50-A 37-40","AES50-A 45-48",
            "AES50-B 5-8","AES50-B 13-16","AES50-B 21-24","AES50-B 29-32","AES50-B 37-40","AES50-B 45-48",
            "Card 5-8","Card 13-16","Card 21-24","Card 29-32","Out 5-8","Out 13-16","P16 5-8","P16 13-16",
            "Aux / Control Room","Aux / Talkback","Ultranet 5-8","Ultranet 13-16","Ultranet 21-24","Ultranet 29-32",
            "Ultranet 37-40","Ultranet 45-48","USB 5-8","USB 13-16","USB 21-24","USB 29-32"),
}
OUT_PATCH_CHOICES["9-12"] = OUT_PATCH_CHOICES["1-4"]
OUT_PATCH_CHOICES["13-16"] = OUT_PATCH_CHOICES["5-8"]
for bank in OUTPUT_BLOCKS:
    ROUTING_PATHS[f"/config/routing/OUT/{bank}"] = ("Output patch " + bank, OUT_PATCH_CHOICES[bank])
for bank in ("1-8", "9-16", "17-24", "25-32"):
    ROUTING_PATHS[f"/config/routing/PLAY/{bank}"] = ("Playback patch", INPUT_BANKS)
ROUTING_PATHS["/config/routing/PLAY/AUX"] = ("Playback Aux patch", AUX_INPUT_BANKS)
ROUTING_PATHS["/config/routing/outswitch"] = ("Routing mode", ("Record", "Playback"))
ROUTING_PATHS["/config/routing/routswitch"] = ("Routing mode", ("Record", "Playback"))
ROUTING_PATHS["/config/routing/rootswitch"] = ("Routing mode", ("Record", "Playback"))

# X32node scene text uses symbolic enum tokens, while direct OSC parameter
# SETs use the corresponding integer enum indices. Keep protocol tokens
# separate from the friendlier labels used by the routing dashboard.
INPUT_PATCH_TOKENS = (
    "AN1-8", "AN9-16", "AN17-24", "AN25-32",
    "A1-8", "A9-16", "A17-24", "A25-32", "A33-40", "A41-48",
    "B1-8", "B9-16", "B17-24", "B25-32", "B33-40", "B41-48",
    "CARD1-8", "CARD9-16", "CARD17-24", "CARD25-32",
    "UIN1-8", "UIN9-16", "UIN17-24", "UIN25-32",
)
AUX_INPUT_PATCH_TOKENS = (
    "AUX1-4", "AN1-2", "AN1-4", "AN1-6", "A1-2", "A1-4", "A1-6",
    "B1-2", "B1-4", "B1-6", "CARD1-2", "CARD1-4", "CARD1-6",
    "UIN1-2", "UIN1-4", "UIN1-6",
)
AES50_OUTPUT_PATCH_TOKENS = (
    "AN1-8", "AN9-16", "AN17-24", "AN25-32",
    "A1-8", "A9-16", "A17-24", "A25-32", "A33-40", "A41-48",
    "B1-8", "B9-16", "B17-24", "B25-32", "B33-40", "B41-48",
    "CARD1-8", "CARD9-16", "CARD17-24", "CARD25-32",
    "OUT1-8", "OUT9-16", "P161-8", "P169-16",
    "AUX1-6/Mon", "AUXIN1-6/TB",
    "UOUT1-8", "UOUT9-16", "UOUT17-24", "UOUT25-32", "UOUT33-40", "UOUT41-48",
    "UIN1-8", "UIN9-16", "UIN17-24", "UIN25-32",
)
OUT_PATCH_TOKENS = {
    "1-4": (
        "AN1-4", "AN9-12", "AN17-20", "AN25-28",
        "A1-4", "A9-12", "A17-20", "A25-28", "A33-36", "A41-44",
        "B1-4", "B9-12", "B17-20", "B25-28", "B33-36", "B41-44",
        "CARD1-4", "CARD9-12", "CARD17-20", "CARD25-28",
        "OUT1-4", "OUT9-12", "P161-4", "P169-12", "AUX/CR", "AUX/TB",
        "UOUT1-4", "UOUT9-12", "UOUT17-20", "UOUT25-28", "UOUT33-36", "UOUT41-44",
        "UIN1-4", "UIN9-12", "UIN17-20", "UIN25-28",
    ),
    "5-8": (
        "AN5-8", "AN13-16", "AN21-24", "AN29-32",
        "A5-8", "A13-16", "A21-24", "A29-32", "A37-40", "A45-48",
        "B5-8", "B13-16", "B21-24", "B29-32", "B37-40", "B45-48",
        "CARD5-8", "CARD13-16", "CARD21-24", "CARD29-32",
        "OUT5-8", "OUT13-16", "P165-8", "P1613-16", "AUX/CR", "AUX/TB",
        "UOUT5-8", "UOUT13-16", "UOUT21-24", "UOUT29-32", "UOUT37-40", "UOUT45-48",
        "UIN5-8", "UIN13-16", "UIN21-24", "UIN29-32",
    ),
}
OUT_PATCH_TOKENS["9-12"] = OUT_PATCH_TOKENS["1-4"]
OUT_PATCH_TOKENS["13-16"] = OUT_PATCH_TOKENS["5-8"]

ROUTING_ENUM_TOKENS = {}
for bank in ("1-8", "9-16", "17-24", "25-32"):
    ROUTING_ENUM_TOKENS[f"/config/routing/IN/{bank}"] = INPUT_PATCH_TOKENS
    ROUTING_ENUM_TOKENS[f"/config/routing/PLAY/{bank}"] = INPUT_PATCH_TOKENS
ROUTING_ENUM_TOKENS["/config/routing/IN/AUX"] = AUX_INPUT_PATCH_TOKENS
ROUTING_ENUM_TOKENS["/config/routing/PLAY/AUX"] = AUX_INPUT_PATCH_TOKENS
for family in ("AES50A", "AES50B", "CARD"):
    for bank in ("1-8", "9-16", "17-24", "25-32", "33-40", "41-48"):
        path = f"/config/routing/{family}/{bank}"
        if path in ROUTING_PATHS:
            ROUTING_ENUM_TOKENS[path] = AES50_OUTPUT_PATCH_TOKENS
for bank, tokens in OUT_PATCH_TOKENS.items():
    ROUTING_ENUM_TOKENS[f"/config/routing/OUT/{bank}"] = tokens
for switch in ("outswitch", "routswitch", "rootswitch"):
    ROUTING_ENUM_TOKENS[f"/config/routing/{switch}"] = ("REC", "PLAY")


def routing_enum_index(address, value):
    """Convert an X32node symbolic routing enum or numeric OSC enum to its index."""
    tokens = ROUTING_ENUM_TOKENS.get(address)
    if tokens is None:
        raise ValueError("No routing enum token table for %s" % address)
    if isinstance(value, bool):
        raise ValueError("Boolean is not a routing enum")
    if isinstance(value, int):
        index = value
    elif isinstance(value, float) and value.is_integer():
        index = int(value)
    elif isinstance(value, str):
        try:
            index = tokens.index(value)
        except ValueError:
            # M32-Edit uses the shorter AUX/TB spelling in some AES50
            # routing scene dumps for the same enum slot documented as
            # AUXIN1-6/TB by the protocol reference.
            aliases = {"AUX/TB": "AUXIN1-6/TB"}
            try:
                index = tokens.index(aliases[value])
            except (KeyError, ValueError):
                try:
                    index = int(value, 0)
                except ValueError:
                    raise ValueError("Unknown routing enum token %r for %s" % (value, address))
    else:
        raise ValueError("Invalid routing enum value %r for %s" % (value, address))
    if not 0 <= index < len(tokens):
        raise ValueError("Routing enum index %d is out of range for %s" % (index, address))
    return index


def routing_enum_token(address, value):
    """Return the protocol symbolic token for a stored routing enum index."""
    tokens = ROUTING_ENUM_TOKENS.get(address)
    if tokens is None:
        return str(value)
    index = routing_enum_index(address, value)
    return tokens[index]

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
        if address in CONFIG_LINK_ADDRESSES:
            # Stereo-link controls are binary. Keep them in the routing inventory,
            # but do not let this generic inventory path bypass ConsoleState validation.
            if (not isinstance(value, (int, float)) or isinstance(value, bool)
                    or float(value) not in (0.0, 1.0)):
                return False
            self.values[address] = int(value)
            return True
        if (address.startswith(("/config/routing/", "/outputs/", "/config/userrout/",
                                  "/fx/", "/config/solo/", "/config/talk/",
                                  "/main/m/mix/pan")) or
                (address.startswith(("/ch/", "/auxin/", "/fxrtn/", "/bus/")) and
                 (address.endswith("/insert") or address.endswith("/mix/pan")))):
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
        for family, count in (("main", 16), ("aux", 6), ("p16", 16), ("aes", 2)):
            for number in range(1, count + 1):
                prefix = f"/outputs/{family}/{number:02d}"
                for suffix, title, choices in (("src", "source", OUTPUT_SOURCES),
                                               ("pos", "tap", OUTPUT_TAPS)):
                    address = prefix + "/" + suffix
                    known = address in self.values
                    value = self.values.get(address)
                    outputs.append({"address": address, "label": f"{family.upper()} {number:02d} {title}",
                                    "known": known, "value": value,
                                    "display": _enum_label(value, choices) if known else "Not received"})
                output_suffixes = ["invert"]
                if family == "main":
                    output_suffixes.extend(("delay/on", "delay/time"))
                for suffix in output_suffixes:
                    address = prefix + "/" + suffix
                    known = address in self.values
                    value = self.values.get(address)
                    outputs.append({"address": address, "label": f"{family.upper()} {number:02d} {suffix}",
                                    "known": known, "value": value,
                                    "display": str(value) if known else "Not received"})
                if family == "p16":
                    for suffix in ("iQ/group", "iQ/speaker", "iQ/eq"):
                        address = prefix + "/" + suffix
                        known = address in self.values
                        value = self.values.get(address)
                        outputs.append({"address": address, "label": f"P16 {number:02d} {suffix}",
                                        "known": known, "value": value,
                                        "display": str(value) if known else "Not received"})
        fx = []
        for number in range(1, 9):
            for suffix in ("type", "source", "par"):
                address = f"/fx/{number}/{suffix}"
                fx.append({"address": address, "label": f"FX {number} {suffix}",
                           "known": address in self.values, "value": self.values.get(address),
                           "display": str(self.values[address]) if address in self.values else "Not received"})
        special = []
        for address, value in sorted(self.values.items()):
                special.append({"address": address, "value": value})
        total = len(ROUTING_PATHS) + len(outputs) + len(fx)
        known = sum(1 for a in ROUTING_PATHS if a in self.values) + sum(1 for x in outputs if x["known"]) + sum(1 for x in fx if x["known"])
        return {"sections": [{"name": name, "items": items} for name, items in sections.items()],
                "outputs": outputs, "effects": fx, "special": special,
                "known": known, "total": total, "complete": known == total}
