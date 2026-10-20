"""
Normalisation d'un fichier de scan vers des blocs de contenu acceptes par l'API
Claude (image base64 ou document PDF base64).

- PDF : transmis tel quel (Claude lit le PDF nativement).
- Images (jpg/png/webp/gif) : auto-rotation EXIF, downscale, re-encodage JPEG.
- TIFF : converti page par page en images (l'import DiameX convertit deja les
  TIFF en PDF, ce chemin n'est qu'un filet de securite).
"""
from __future__ import annotations

import base64
import io
import os

from django.conf import settings

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = None
    ImageOps = None

# Limites API Claude
MAX_PDF_BYTES = 32 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_TIFF_PAGES = 8

_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
_TIFF_EXT = {".tif", ".tiff"}


class UnsupportedScan(Exception):
    """Le fichier n'est pas un justificatif exploitable (format inconnu, vide, corrompu)."""


def _sniff(data: bytes, filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if data[:5] == b"%PDF-" or ext == ".pdf":
        return "pdf"
    if data[:4] in (b"II*\x00", b"MM\x00*") or ext in _TIFF_EXT:
        return "tiff"
    if ext in _IMAGE_EXT:
        return "image"
    if data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:4] == b"RIFF":
        return "image"
    return "unknown"


def _edge() -> int:
    return int(getattr(settings, "AI_PREFILL_MAX_IMAGE_EDGE", 1568) or 1568)


def _pil_to_block(img) -> dict:
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    edge = _edge()
    if max(img.size) > edge:
        ratio = edge / max(img.size)
        img = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))))
    buf = io.BytesIO()
    quality = 85
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    while buf.tell() > MAX_IMAGE_BYTES and quality > 40:
        quality -= 15
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.standard_b64encode(buf.getvalue()).decode("ascii"),
        },
    }


def build_content_blocks(data: bytes, filename: str = "") -> list[dict]:
    """Retourne la liste de blocs `content` (document/image) pour un message user."""
    if not data:
        raise UnsupportedScan("Fichier vide")

    kind = _sniff(data, filename)

    if kind == "pdf":
        if len(data) > MAX_PDF_BYTES:
            raise UnsupportedScan(f"PDF trop volumineux ({len(data) // (1024*1024)} Mo > 32 Mo)")
        return [{
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.standard_b64encode(data).decode("ascii"),
            },
        }]

    if Image is None:
        raise UnsupportedScan("Pillow requis pour traiter les images")

    if kind == "tiff":
        blocks: list[dict] = []
        with Image.open(io.BytesIO(data)) as img:
            pages = min(getattr(img, "n_frames", 1) or 1, MAX_TIFF_PAGES)
            for i in range(pages):
                img.seek(i)
                blocks.append(_pil_to_block(img.copy()))
        if not blocks:
            raise UnsupportedScan("TIFF illisible")
        return blocks

    if kind == "image":
        try:
            with Image.open(io.BytesIO(data)) as img:
                return [_pil_to_block(img.copy())]
        except Exception as exc:  # noqa: BLE001
            raise UnsupportedScan(f"Image illisible : {exc}") from exc

    # dernier recours : laisser PIL tenter
    try:
        with Image.open(io.BytesIO(data)) as img:
            return [_pil_to_block(img.copy())]
    except Exception as exc:  # noqa: BLE001
        raise UnsupportedScan(f"Format non reconnu ({filename or 'sans nom'})") from exc
