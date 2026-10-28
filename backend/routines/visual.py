"""Finding a routine's recorded picture of a target on the current screen (Phase 6, routines on screens with no tree).

Normalized cross-correlation (numpy FFT) of the recorded crop over the screenshot, both in device pixels and scaled
by the ratio of screen densities, so a picture recorded on one phone is the right size on another. A match counts only
when it is clear (score ≥ 0.9) and unique (no other place within 0.04 of it): on a seat map every "A" seat looks the
same, and then the executor asks grounding instead of guessing.
"""

from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image

MIN_SCORE = 0.90
UNIQUE_GAP = 0.04
WORK_SCALE = 0.5  # match at half resolution: ~4x faster, and still a few pixels of precision


def _gray(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("L"), dtype=np.float64)


def ncc(image: np.ndarray, template: np.ndarray) -> np.ndarray:
    """Normalized cross-correlation of `template` at every position where it fits in `image` (values -1..1).
    Windows with almost no contrast (a flat background) score 0: dividing by their near-zero variance is noise."""
    image, template = image.astype(np.float64), template.astype(np.float64)
    ih, iw = image.shape
    th, tw = template.shape
    t = template - template.mean()
    t_norm = float(np.sqrt((t * t).sum()))
    if t_norm == 0 or th > ih or tw > iw:
        return np.zeros((max(0, ih - th + 1), max(0, iw - tw + 1)), dtype=np.float32)
    fh, fw = ih + th - 1, iw + tw - 1
    corr = np.fft.irfft2(np.fft.rfft2(image, (fh, fw)) * np.conj(np.fft.rfft2(t, (fh, fw))), (fh, fw))[: ih - th + 1, : iw - tw + 1]
    # Local sums of the image under the template, from integral images.
    def window_sum(a: np.ndarray) -> np.ndarray:
        c = np.pad(a.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        return c[th:, tw:] - c[:-th, tw:] - c[th:, :-tw] + c[:-th, :-tw]
    n = th * tw
    s1, s2 = window_sum(image), window_sum(image * image)
    var = s2 - s1 * s1 / n
    flat = var < 0.05 * t_norm * t_norm  # under 5% of the template's own contrast
    out = corr / (np.sqrt(np.maximum(var, 1e-9)) * t_norm)
    out[flat] = 0.0
    return np.clip(out, -1.0, 1.0).astype(np.float32)


def match_crop(screen_png: bytes, crop_b64: str, size: tuple[int, int], scale: float = 1.0) -> tuple[tuple[int, int] | None, float, float]:
    """(center in device pixels or None, best score, runner-up score)."""
    screen = Image.open(io.BytesIO(screen_png)).convert("RGB")
    if screen.size != size:
        screen = screen.resize(size)
    crop = Image.open(io.BytesIO(base64.b64decode(crop_b64))).convert("RGB")
    k = scale * WORK_SCALE
    crop = crop.resize((max(4, round(crop.width * k)), max(4, round(crop.height * k))))
    work = screen.resize((max(8, round(size[0] * WORK_SCALE)), max(8, round(size[1] * WORK_SCALE))))
    scores = ncc(_gray(work), _gray(crop))
    if scores.size == 0:
        return None, 0.0, 0.0
    y, x = np.unravel_index(int(np.argmax(scores)), scores.shape)
    best = float(scores[y, x])
    masked = scores.copy()
    y0, y1 = max(0, y - crop.height // 2), y + crop.height // 2 + 1
    x0, x1 = max(0, x - crop.width // 2), x + crop.width // 2 + 1
    masked[y0:y1, x0:x1] = -1
    second = float(masked.max()) if masked.size else -1.0
    if best < MIN_SCORE or best - second < UNIQUE_GAP:
        return None, best, second
    cx = (x + crop.width / 2) / WORK_SCALE
    cy = (y + crop.height / 2) / WORK_SCALE
    return (round(cx), round(cy)), best, second


def encode(png: bytes) -> str:
    return base64.b64encode(png).decode()
