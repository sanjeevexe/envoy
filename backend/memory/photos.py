"""Photos and screenshots → facts (design doc, Shared memory › Getting facts in: "iPhone photos"; Safety › Photos).

Only images you pick or share reach this module. For each one:
1. **Read the text on this Mac** with Apple's Vision framework (`memory/ocr.swift`, compiled once to data/bin/envoy-ocr).
   Words on one row are joined ("Seat · 14C"), so a label and its value stay together.
2. **Redact before anything leaves the Mac**: lines with a card number, a sign-in code or an ID number are blacked out
   in the copy of the image sent to the model, and redacted in the text that is kept.
3. **Muse Spark reads the image** with the text beside it and returns entities (the same types and schema as screens).
4. **Check every value against the image's text**: a value Vision didn't read is dropped, not stored.
5. **Store** through the memory service with a `photo` source (the redacted text is its snapshot, so every fact stays
   traceable); natural keys put a boarding pass on the trip and flight memory already knows.
6. **Delete the image**, whether or not anything was extracted. The caller passes a path; it is gone when this returns.
"""

from __future__ import annotations

import asyncio
import io
import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps

from memory import extract
from memory.redact import redact_text
from memory.service import IngestReport, MemoryService
from memory.types import TYPES
from models.adapter import image_part
from models.prompts import extract_input, extract_instructions

REPO = Path(__file__).resolve().parents[2]
OCR_SRC = Path(__file__).with_name("ocr.swift")
OCR_BIN = REPO / "data" / "bin" / "envoy-ocr"
MODEL_MAX_SIDE = 1600  # long side of the copy sent to the model (a phone screenshot: about 1,500 tokens)

PHOTO_NOTE = """
This source is a photo or screenshot the user shared. You get the image and the text read from it on the user's device,
one row per line ("Seat · 14C" means the label Seat and the value 14C). Copy values exactly as that text writes them;
evidence is null. Status-bar text (the clock, battery) and app chrome are not facts. A boarding pass or trip screen is
the user's own booking: return the Flight (number as written, e.g. "SL 482"; date; from; to; seat; gate; boarding_time;
boarding_group as the group alone, "3" for "Group 3") and its Trip (confirmation_code if shown; destination city if
written), and the passenger as a Person.
"""


@dataclass
class OcrLine:
    text: str
    confidence: float
    box: tuple[float, float, float, float]  # x, y, w, h as fractions; origin top left


@dataclass
class PhotoResult:
    photo_id: str
    report: IngestReport | None
    text: str  # redacted rows, as kept in the source snapshot
    lines: int
    redacted_lines: int
    ocr_ms: float
    model_ms: float
    deleted: bool
    skipped: str = ""
    timings: dict[str, float] = field(default_factory=dict)


def ocr_binary() -> Path:
    """The OCR helper, compiled from ocr.swift the first time (and again whenever the source changes)."""
    if not OCR_BIN.exists() or OCR_BIN.stat().st_mtime < OCR_SRC.stat().st_mtime:
        OCR_BIN.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["swiftc", "-O", str(OCR_SRC), "-o", str(OCR_BIN)], check=True, capture_output=True, timeout=300)
    return OCR_BIN


def read_text(path: Path) -> tuple[int, int, list[OcrLine]]:
    out = subprocess.run([str(ocr_binary()), str(path)], check=True, capture_output=True, timeout=60).stdout
    d = json.loads(out)
    return d["width"], d["height"], [OcrLine(x["text"], float(x["confidence"]), tuple(x["box"])) for x in d["lines"]]  # type: ignore[arg-type]


def rows(lines: list[OcrLine]) -> list[list[OcrLine]]:
    """Group lines into visual rows: a line whose vertical center falls inside the row's band joins it."""
    out: list[list[OcrLine]] = []
    for ln in sorted(lines, key=lambda l: (l.box[1] + l.box[3] / 2, l.box[0])):
        cy = ln.box[1] + ln.box[3] / 2
        if out:
            last = out[-1]
            top = min(l.box[1] for l in last)
            bottom = max(l.box[1] + l.box[3] for l in last)
            if top - 0.15 * (bottom - top) <= cy <= bottom + 0.15 * (bottom - top):
                last.append(ln)
                continue
        out.append([ln])
    return [sorted(r, key=lambda l: l.box[0]) for r in out]


def text_of(lines: list[OcrLine]) -> tuple[str, list[OcrLine]]:
    """The image's text, one row per line, redacted; and the lines that redaction flagged."""
    flagged = [l for l in lines if redact_text(l.text) != l.text]
    text = "\n".join(" · ".join(l.text.strip() for l in r) for r in rows(lines))
    return redact_text(text), flagged


def model_image(img: Image.Image, flagged: list[OcrLine]) -> bytes:
    """The copy that goes to the model: flagged lines blacked out, the long side at most MODEL_MAX_SIDE, JPEG."""
    img = img.convert("RGB")
    if flagged:
        draw = ImageDraw.Draw(img)
        w, h = img.size
        for l in flagged:
            x, y, bw, bh = l.box
            draw.rectangle([x * w - 4, y * h - 4, (x + bw) * w + 4, (y + bh) * h + 4], fill="black")
    scale = MODEL_MAX_SIDE / max(img.size)
    if scale < 1:
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def looks_like_camera_photo(img: Image.Image) -> bool:
    """Screenshots carry no camera make or model; camera photos do."""
    try:
        exif = img.getexif()
    except Exception:  # noqa: BLE001
        return False
    return bool(exif.get(0x010F) or exif.get(0x0110))  # Make, Model


async def ingest_photo(svc: MemoryService, path: Path, *, photo_id: str, origin: str, device: str = "",
                       allow_camera_photos: bool = False, task_id: str | None = None) -> PhotoResult:
    """Read one image into memory and delete it. `origin` says how it arrived (picker, shortcut)."""
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    report: IngestReport | None = None
    text, lines, flagged, ocr_ms, model_ms, skipped = "", [], [], 0.0, 0.0, ""
    try:
        with Image.open(path) as raw:
            img = ImageOps.exif_transpose(raw)
            img.load()
            camera = looks_like_camera_photo(raw)
        if camera and not allow_camera_photos:
            skipped = "this looks like a camera photo; Settings allows screenshots only"
        else:
            t = time.perf_counter()
            _, _, lines = await asyncio.to_thread(read_text, path)
            ocr_ms = (time.perf_counter() - t) * 1000
            text, flagged = text_of(lines)
            if not text.strip():
                skipped = "no text in the image"
            else:
                jpeg = model_image(img, flagged)
                t = time.perf_counter()
                header = f"{'screenshot' if not camera else 'photo'} shared from {device or 'your device'} ({origin})"
                content = [image_part(jpeg, "image/jpeg"),
                           {"type": "input_text", "text": extract_input("photo", header, text[:extract.MAX_SOURCE_CHARS])}]
                res = await asyncio.to_thread(svc.adapter.call, "extract", content, instructions=extract_instructions(extract.type_catalog()) + PHOTO_NOTE,
                                              data_scope="real", task_id=task_id or photo_id)
                model_ms = (time.perf_counter() - t) * 1000
                ents, dropped = extract._from_output(res.parsed, text, None)  # type: ignore[arg-type]
                ex = extract.Extraction(ents, "model", dropped, 1, res.cost_at_standard_usd)
                when = svc.store.clock()
                src = svc.store.add_source("photo", {"photo_id": photo_id, "origin": origin, "device": device, "lines": len(lines)},
                                           captured_at=when, snapshot=text[:4000])
                report = await svc._apply(ex, src, when, "photo")
    finally:
        path.unlink(missing_ok=True)  # the image is never kept
    timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return PhotoResult(photo_id, report, text, len(lines), len(flagged), round(ocr_ms, 1), round(model_ms, 1), not path.exists(),
                       skipped, timings)


def summary(res: PhotoResult, memory: Any) -> str:
    """One line for the Shortcut's notification and the app: what was saved where."""
    if res.skipped:
        return f"Nothing saved: {res.skipped}."
    rep = res.report
    if rep is None or not rep.resolved:
        return "Nothing to remember in that image."
    names = []
    for r in rep.resolved:
        e = memory.entity(memory.resolve(r.entity)) or {}
        names.append(f"{e.get('type', r.type)} {e.get('name') or ''}".strip() + (" (new)" if r.how == "new" else ""))
    new = rep.facts.get("new", 0) + rep.facts.get("replaced", 0)
    same = rep.facts.get("same", 0)
    return f"Saved to {', '.join(dict.fromkeys(names))}: {new} new, {same} confirmed."


__all__ = ["ingest_photo", "summary", "read_text", "text_of", "rows", "PhotoResult", "TYPES"]
