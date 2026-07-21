"""
File storage abstraction.

Local filesystem for now; the interface is deliberately small (`save`) so a
production build can drop in an S3/MinIO backend without touching the API layer.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO

STORAGE_ROOT = Path(__file__).resolve().parent.parent / "storage"


def save(case_id: str, filename: str, fileobj: BinaryIO) -> str:
    """Persist an uploaded file under storage/<case_id>/ and return its path."""
    case_dir = STORAGE_ROOT / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    dest = case_dir / filename
    with dest.open("wb") as out:
        shutil.copyfileobj(fileobj, out)
    return str(dest)
