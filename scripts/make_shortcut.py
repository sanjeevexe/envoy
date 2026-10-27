"""Build the "Send to Envoy" iOS Shortcut (design doc, iPhone companion › Screenshots and photos).

  uv run --project backend python scripts/make_shortcut.py     # → data/api/shortcut/Send to Envoy.shortcut (signed)
  uv run --project backend python scripts/make_shortcut.py --code-test   # the sign-in-code test's shortcut
  open "data/api/shortcut/Send to Envoy.shortcut"               # Shortcuts asks to add it; iCloud brings it to the iPhone

The shortcut appears in the Share Sheet for images. It posts the shared image to Envoy's tailnet address with a
device token that can only upload images (it can't read memory, approve or start tasks), then shows Envoy's one-line
answer ("Saved to Flight SL 482 …") as a notification. The token is made here through the API (the script reads your
session itself and never prints it) and lives only in the signed file and the shortcut; revoke it in Devices.
"""

from __future__ import annotations

import plistlib
import subprocess
import sys
import uuid
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8700"
OUT = REPO / "data" / "api" / "shortcut"


def text(s: str) -> dict:
    return {"Value": {"string": s, "attachmentsByRange": {}}, "WFSerializationType": "WFTextTokenString"}


def workflow(upload_url: str, token: str) -> dict:
    post_id, value_id = str(uuid.uuid4()).upper(), str(uuid.uuid4()).upper()
    header = {"WFItemType": 0, "WFKey": text("Authorization"), "WFValue": text(f"Bearer {token}")}
    return {
        "WFWorkflowClientVersion": "2607.0.2",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowIcon": {"WFWorkflowIconStartColor": 255, "WFWorkflowIconGlyphNumber": 61440},
        "WFWorkflowTypes": ["ActionExtension"],
        "WFWorkflowInputContentItemClasses": ["WFImageContentItem"],
        "WFWorkflowHasShortcutInputVariables": True,
        "WFWorkflowImportQuestions": [],
        "WFQuickActionSurfaces": [],
        "WFWorkflowActions": [
            {"WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
             "WFWorkflowActionParameters": {
                 "UUID": post_id, "WFURL": upload_url, "WFHTTPMethod": "POST", "WFHTTPBodyType": "File", "ShowHeaders": True,
                 "WFRequestVariable": {"Value": {"Type": "ExtensionInput"}, "WFSerializationType": "WFTextTokenAttachment"},
                 "WFHTTPHeaders": {"Value": {"WFDictionaryFieldValueItems": [header]}, "WFSerializationType": "WFDictionaryFieldValue"}}},
            {"WFWorkflowActionIdentifier": "is.workflow.actions.getvalueforkey",
             "WFWorkflowActionParameters": {
                 "UUID": value_id, "WFDictionaryKey": "summary",
                 "WFInput": {"Value": {"OutputUUID": post_id, "Type": "ActionOutput", "OutputName": "Contents of URL"},
                             "WFSerializationType": "WFTextTokenAttachment"}}},
            {"WFWorkflowActionIdentifier": "is.workflow.actions.notification",
             "WFWorkflowActionParameters": {
                 "WFNotificationActionTitle": "Envoy",
                 "WFNotificationActionBody": {"Value": {"string": "￼", "attachmentsByRange": {
                     "{0, 1}": {"OutputUUID": value_id, "Type": "ActionOutput", "OutputName": "Dictionary Value"}}},
                     "WFSerializationType": "WFTextTokenString"}}},
        ],
    }


def code_test_workflow(url: str, token: str) -> dict:
    """The sign-in-code test (Phase 5, an open question): a message automation runs this with the message as input;
    it posts the text to /api/codes/test, which records only that a message with "code" arrived, and when."""
    field = {"Value": {"string": "\ufffc", "attachmentsByRange": {"{0, 1}": {"Type": "ExtensionInput"}}}, "WFSerializationType": "WFTextTokenString"}
    header = {"WFItemType": 0, "WFKey": text("Authorization"), "WFValue": text(f"Bearer {token}")}
    return {
        "WFWorkflowClientVersion": "2607.0.2", "WFWorkflowMinimumClientVersion": 900, "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowIcon": {"WFWorkflowIconStartColor": 4282601983, "WFWorkflowIconGlyphNumber": 61440},
        "WFWorkflowTypes": [], "WFWorkflowInputContentItemClasses": ["WFStringContentItem", "WFGenericFileContentItem"],
        "WFWorkflowHasShortcutInputVariables": True, "WFWorkflowImportQuestions": [], "WFQuickActionSurfaces": [],
        "WFWorkflowActions": [
            {"WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
             "WFWorkflowActionParameters": {
                 "UUID": str(uuid.uuid4()).upper(), "WFURL": url, "WFHTTPMethod": "POST", "WFHTTPBodyType": "JSON", "ShowHeaders": True,
                 "WFJSONValues": {"Value": {"WFDictionaryFieldValueItems": [{"WFItemType": 0, "WFKey": text("message"), "WFValue": field}]},
                                  "WFSerializationType": "WFDictionaryFieldValue"},
                 "WFHTTPHeaders": {"Value": {"WFDictionaryFieldValueItems": [header]}, "WFSerializationType": "WFDictionaryFieldValue"}}},
        ],
    }


def main() -> int:
    code_test = "--code-test" in sys.argv
    session = (REPO / "data" / "api" / "session_token").read_text().strip()
    scope, name = ("code_test", "Envoy code test (iOS automation)") if code_test else ("photos", "Send to Envoy (iOS Shortcut)")
    r = httpx.post(f"{BASE}/api/tokens", json={"scope": scope, "name": name}, headers={"Authorization": f"Bearer {session}"}, timeout=30)
    r.raise_for_status()
    got = r.json()
    if not got["upload_url"].startswith("https://"):
        print("Envoy isn't on the tailnet (scripts/serve_tailnet.sh on, then restart the API)", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    OUT.chmod(0o700)
    unsigned, signed = OUT / "unsigned.shortcut", OUT / ("Envoy code test.shortcut" if code_test else "Send to Envoy.shortcut")
    flow = code_test_workflow(got["upload_url"].replace("/api/photos", "/api/codes/test"), got["token"]) if code_test else workflow(got["upload_url"], got["token"])
    unsigned.write_bytes(plistlib.dumps(flow, fmt=plistlib.FMT_BINARY))
    signed.unlink(missing_ok=True)
    subprocess.run(["shortcuts", "sign", "--mode", "people-who-know-me", "--input", str(unsigned), "--output", str(signed)], check=True)
    unsigned.unlink()
    signed.chmod(0o600)
    print(f"signed: {signed}\nuploads to: {got['upload_url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
