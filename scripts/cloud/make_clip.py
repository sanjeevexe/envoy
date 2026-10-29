"""The cloud clip for the video: the VM's terminal on the left, revealed in real time, and the emulator on the right.

  uv run --project backend python scripts/cloud/make_clip.py   # needs ffmpeg; run on the Mac

Reads eval/results/cloud/clip/{emulator.mp4,terminal.tsv} (scripts/cloud/vm-clip.sh records both on the VM, on one
clock) and writes eval/results/cloud/clip/cloud-clip.mp4: 1920x1080, 30 fps, real time, no sound. Nothing is sped up.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
CLIP = REPO / "eval" / "results" / "cloud" / "clip"
W, H, PHONE_W = 1920, 1080, 486  # the phone: 1080x2400 scaled to the frame's height
LEFT_W = W - PHONE_W
FPS_LEFT = 10
START, END = 2.5, 43.0  # seconds of the recording to keep: the first routine starts at ~2 s, the last PASS is at 42.5 s
MONO = "/System/Library/Fonts/Menlo.ttc"
SANS = "/System/Library/Fonts/Helvetica.ttc"
BG, FG, DIM, GREEN, RED, BLUE = "#0d1117", "#e6edf3", "#8b949e", "#3fb950", "#f85149", "#79c0ff"
ROW = re.compile(r"^(PASS|FAIL) port-\S+ (\S+)\s+v\d+ (\S+)\s+(\S+)\s+rung=(\d+) calls=(\d+) \$[\d.]+\s+([\d.]+)s\s+'?([^']*)")


def lines() -> list[tuple[float, str, str]]:
    """(time, text, colour) for each transcript line, routine rows made short enough to read in a video."""
    out = []
    for raw in (CLIP / "terminal.tsv").read_text().splitlines():
        t, text = raw.split("\t", 1)
        if m := ROW.match(text):
            verdict, routine, city, _status, rung, calls, secs, answer = m.groups()
            answer = answer.split(" · ")[0].rstrip()
            text = f"{verdict}  {routine:<12} {city:<8} {calls} model calls  {float(secs):4.1f} s  {answer}"
            colour = GREEN if verdict == "PASS" else RED
        elif text.startswith("$"):
            text, colour = text.replace(" --device envoy-test", "").replace(" --k 1", ""), BLUE  # fits beside the phone
        elif text.startswith("=="):
            text, colour = text.replace("== ", ""), DIM
        else:
            colour = FG
        out.append((float(t), text.replace("\t", "  "), colour))
    return out


def frame(now: float, rows: list[tuple[float, str, str]], fonts: dict[str, ImageFont.FreeTypeFont]) -> Image.Image:
    img = Image.new("RGB", (LEFT_W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((60, 52), "Envoy, running on Google Cloud", font=fonts["title"], fill=FG)
    d.text((60, 118), "The phone on the right is an Android emulator on this server, not on a Mac.", font=fonts["sub"], fill=DIM)
    y = 200
    shown = [r for r in rows if r[0] <= now]
    for _, text, colour in shown:
        d.text((60, y), text, font=fonts["mono"], fill=colour)
        y += 40
    if int(now * 2) % 2 == 0:  # a blinking cursor under the last line
        d.rectangle((60, y + 6, 74, y + 32), fill=FG)
    d.text((60, H - 112), "Real time. SkyLark routines compiled on a Mac, run unchanged.", font=fonts["sub"], fill=DIM)
    d.text((60, H - 70), f"{now - START:4.1f} s", font=fonts["sub"], fill=DIM)
    return img


def main() -> int:
    if not shutil.which("ffmpeg"):
        print("needs ffmpeg", file=sys.stderr)
        return 1
    fonts = {"title": ImageFont.truetype(SANS, 52), "sub": ImageFont.truetype(SANS, 28), "mono": ImageFont.truetype(MONO, 24)}
    rows = lines()
    with tempfile.TemporaryDirectory() as tmp:
        n = int((END - START) * FPS_LEFT)
        for i in range(n):
            frame(START + i / FPS_LEFT, rows, fonts).save(Path(tmp) / f"l{i:04d}.png")
        out = CLIP / "cloud-clip.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y",
                        "-framerate", str(FPS_LEFT), "-i", str(Path(tmp) / "l%04d.png"),
                        "-ss", str(START), "-t", str(END - START), "-i", str(CLIP / "emulator.mp4"),
                        "-filter_complex", f"[0:v]fps=30[l];[1:v]fps=30,scale={PHONE_W}:{H}[r];[l][r]hstack=inputs=2,format=yuv420p[v]",
                        "-map", "[v]", "-an", "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-t", str(END - START), str(out)],
                       check=True)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
