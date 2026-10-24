import re

TAGS = ["REPLY", "BUDGET", "AREA", "TIMELINE", "HANDOFF", "SLOT"]
PATTERN = r"^\s*(" + "|".join(TAGS) + r")\s*:\s*"
EMPTY = {"", "none", "null", "n/a", "unknown", "-"}


def parse_tagged(raw):
    parts = re.split(PATTERN, raw, flags=re.M | re.I)
    found = {}
    for i in range(1, len(parts) - 1, 2):
        found[parts[i].upper()] = parts[i + 1].strip()
    if not found.get("REPLY"):
        raise ValueError("no REPLY in model output")

    def val(key):
        v = found.get(key, "")
        return None if v.lower() in EMPTY else v

    return {
        "reply": found["REPLY"],
        "budget": val("BUDGET"),
        "area": val("AREA"),
        "timeline": val("TIMELINE"),
        "handoff": found.get("HANDOFF", "").lower().startswith(("yes", "true")),
        "chosen_slot": val("SLOT"),
    }
