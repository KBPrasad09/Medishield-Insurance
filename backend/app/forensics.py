"""
Image forensics for ID documents — Error Level Analysis.

ELA works on one idea: JPEG compression is lossy and *idempotent-ish*. Re-save an
untouched JPEG at a known quality and most of the image barely changes, because
it has already settled into that quantization. But a region that was pasted in,
painted over, or re-rendered has a different compression history, so it moves
much more on the re-save. Amplify that per-pixel difference and edited regions
light up against the rest of the image.

    ela = |original − recompress(original, q)|

What this catches: manipulated photographs and scans — a swapped photo, an
overwritten date on a real ID, a spliced signature.

What it does NOT catch, and this is measured rather than assumed: documents that
were never JPEGs. If an image is a losslessly generated PNG, every pixel has the
same (empty) compression history, so ELA has nothing to contrast. See
`scripts/ela_experiment.py` and `eval/ela_findings.md` for the numbers on this
project's synthetic dataset.

Because of that, `ela_score` is reported as an advisory signal on the KYC output.
It never gates a decision on its own.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops


def ela_map(path: str | Path, quality: int = 90) -> np.ndarray:
    """Per-pixel error level (0–255), max across RGB channels."""
    img = Image.open(path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    recompressed = Image.open(buf)
    diff = ImageChops.difference(img, recompressed)
    return np.asarray(diff, dtype=np.float32).max(axis=2)


def ela_score(path: str | Path, quality: int = 90, block: int = 16) -> dict:
    """
    Summarize an ELA map into features a reviewer can use.

    Scoring is block-wise rather than per-pixel. Manipulation is *localized* — a
    patch of the image behaves unlike the rest — so we average the error over
    16x16 blocks and ask how extreme the worst block is compared with the
    distribution of all blocks, using a median/MAD robust z-score. Per-pixel
    scoring drowns in text edges, which are high-error everywhere on a document.

    `top_z` is the headline number: how many robust deviations the most anomalous
    block sits above the typical block.
    """
    d = ela_map(path, quality)
    h, w = d.shape
    hh, ww = h // block * block, w // block * block
    blocks = d[:hh, :ww].reshape(hh // block, block, ww // block, block).mean(axis=(1, 3))

    v = blocks.ravel()
    median = float(np.median(v))
    mad = float(np.median(np.abs(v - median))) or 0.5
    z = (v - median) / (1.4826 * mad)

    return {
        "top_z": round(float(z.max()), 2),
        "hot_blocks": int((z > 8).sum()),
        "hot_block_pct": round(float((z > 8).mean() * 100), 3),
        "max_error": round(float(d.max()), 1),
        "mean_error": round(float(d.mean()), 2),
    }


def save_ela_image(path: str | Path, out_path: str | Path, quality: int = 90) -> Path:
    """Write a viewable, contrast-stretched ELA image (useful for reviewers)."""
    d = ela_map(path, quality)
    scale = 255.0 / max(d.max(), 1.0)
    out = Image.fromarray((d * scale).astype(np.uint8), mode="L")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(out_path)
    return out_path
