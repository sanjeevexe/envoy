"""The saved-login experiment (docs/preflight-and-autofill.md): what Envoy's screen reading sees at a sign-in screen
when the phone's password manager offers a saved login. Observation first:

    uv run --project backend python eval/autofill_probe.py look  <serial> <label>    # one reading, saved
    uv run --project backend python eval/autofill_probe.py focus <serial> [--id ID]  # tap the username field
    uv run --project backend python eval/autofill_probe.py tap   <serial> <label>    # tap an element by its exact label

- `look` reads the screen the way Envoy's device layer does (the uiautomator tree, the focused window and its
  FLAG_SECURE), plus the window list, and saves them under eval/results/autofill/<date>/. Every text field's contents
  are replaced by their length and whether they are masked before anything is saved or printed. No screenshot.
- `focus` taps the username field (an editable field whose hint, label or id says email, user or phone).
- `tap` taps one element by its exact label. It is for the saved-login suggestion, and only when the user said so in
  the session. It refuses a password field and any sign-in button: the user presses that.

It never types, never reads a field's value into anything but a length, and never signs in.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from devices.android import AndroidDevice  # noqa: E402

OUT = Path(__file__).resolve().parent / "results" / "autofill" / date.today().isoformat()
_USERNAME = re.compile(r"(e-?mail|user|login|phone|mobile|account)", re.I)
_SIGN_IN = re.compile(r"^(sign ?in|log ?in|continue|next|submit)$", re.I)
_BULLETS = re.compile(r"^[•●*·•●]+$")


def _is_field(n: ET.Element) -> bool:
    return "EditText" in n.get("class", "") or n.get("password") == "true"


def redact(xml: str) -> tuple[str, list[dict], set[str]]:
    """The tree with each text field's text replaced by its length (and masked or not), those fields listed, and the
    password fields' own texts (to scrub wherever else they show up, such as a parent's merged label; never saved)."""
    root = ET.fromstring(xml)
    fields = []
    secrets = {n.get("text", "") for n in root.iter("node") if n.get("password") == "true" and n.get("text") and n.get("text") != n.get("hint")}
    for n in root.iter("node"):
        if not _is_field(n):
            continue
        text = n.get("text", "")
        hint = n.get("hint", "") or ""
        shown = "" if text == hint else text  # an empty field shows its hint as its text
        info = {"resource_id": n.get("resource-id", ""), "hint": hint, "password": n.get("password") == "true",
                "focused": n.get("focused") == "true", "chars": len(shown), "masked": bool(shown) and bool(_BULLETS.match(shown)),
                "package": n.get("package", ""), "bounds": n.get("bounds", "")}
        fields.append(info)
        n.set("text", f"[{len(shown)} chars{', masked' if info['masked'] else ''}]" if shown else (hint and f"[empty, hint: {hint}]") or "[empty]")
    for n in root.iter("node"):
        for attr in ("text", "content-desc"):
            n.set(attr, scrub(n.get(attr, ""), secrets))
    return ET.tostring(root, encoding="unicode"), fields, secrets


def scrub(text: str, secrets: set[str]) -> str:
    for sec in secrets:
        if sec and not _BULLETS.match(sec):
            text = text.replace(sec, "[password text]")
    return text


def windows(dev: AndroidDevice) -> list[str]:
    """The window list, top first: titles only (InputMethod, an autofill dropdown, the app, ...)."""
    out = dev.adb.shell("dumpsys window windows | grep -E '^  Window #'")
    return [m.group(1) for m in re.finditer(r"Window\{\w+ u\d+ ([^}]+)\}", out)]


def look(dev: AndroidDevice, label: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    xml = dev._dump()
    pkg, act, secure = dev._foreground()
    state = dev._observe_sync(False)
    clean, fields, secrets = redact(xml)
    app_pkgs = {pkg}
    others = sorted({e.package for e in state.elements if e.package and e.package not in app_pkgs})
    # What isn't the app's: the keyboard's strip, an autofill dropdown, system UI. Only short labels, never field text.
    foreign = [{"package": e.package, "label": scrub(e.label or "", secrets)[:80], "resource_id": e.resource_id, "chrome": e.status_bar,
                "clickable": e.clickable, "bounds": e.bounds}
               for e in state.elements if e.package not in app_pkgs and e.package != "com.android.systemui" and (e.label or e.resource_id)
               and not _is_field_el(e)]
    summary = {"label": label, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "package": pkg, "activity": act, "secure": secure,
               "has_password_field": state.has_password_field, "fields": fields, "windows": windows(dev),
               "other_packages": others, "not_the_app": foreign,
               "password_text_unmasked": any(not _BULLETS.match(sec) for sec in secrets),
               "numbered": [f"{e.number}: {e.kind} {scrub(e.label or '', secrets)[:60]!r}" for e in state.numbered if not _is_field_el(e)]}
    (OUT / f"{label}.xml").write_text(clean)
    (OUT / f"{label}.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


def _is_field_el(e) -> bool:
    return bool(getattr(e, "editable", False) or getattr(e, "password", False))


def focus(dev: AndroidDevice, rid: str | None) -> str:
    state = dev._observe_sync(False)
    for e in state.elements:
        if not e.editable or e.password or not e.visible:
            continue
        if (rid and e.resource_id.endswith(rid)) or (not rid and _USERNAME.search(f"{e.hint} {e.label} {e.resource_id}")):
            x1, y1, x2, y2 = e.bounds
            dev.u2.click((x1 + x2) // 2, (y1 + y2) // 2)
            return f"tapped the field {e.resource_id or e.hint!r}"
    return "no username field found: nothing tapped"


def tap(dev: AndroidDevice, label: str) -> str:
    state = dev._observe_sync(False)
    hits = [e for e in state.elements if e.visible and (e.label or "").strip() == label]
    if len(hits) != 1:
        return f"{len(hits)} elements labelled {label!r}: nothing tapped"
    e = hits[0]
    if e.password or e.editable:
        return "that's a text field: nothing tapped"
    if _SIGN_IN.match(label):
        return "that's the sign-in button: the user presses it"
    x1, y1, x2, y2 = e.bounds
    dev.u2.click((x1 + x2) // 2, (y1 + y2) // 2)
    return f"tapped {label!r} ({e.package})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["look", "focus", "tap"])
    ap.add_argument("serial")
    ap.add_argument("label", nargs="?")
    ap.add_argument("--id")
    a = ap.parse_args()
    dev = AndroidDevice(a.serial).connect()
    if a.what == "look":
        print(json.dumps(look(dev, a.label or time.strftime("%H%M%S")), indent=1, default=str))
    elif a.what == "focus":
        print(focus(dev, a.id))
    else:
        print(tap(dev, a.label or ""))


if __name__ == "__main__":
    main()
