"""把 assets/icon.png 转成 Windows/PyInstaller 能嵌入 exe 的 BMP 型 ICO。"""
from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PNG = ROOT / "assets" / "icon.png"
ICO = ROOT / "assets" / "app.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def _square(im: Image.Image) -> Image.Image:
    im = im.convert("RGBA")
    w, h = im.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return im.crop((left, top, left + side, top + side))


def _dib32(im: Image.Image) -> bytes:
    w, h = im.size
    xor = im.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes("raw", "BGRA")
    and_row = ((w + 31) // 32) * 4
    and_mask = bytes(and_row * h)
    header = struct.pack(
        "<IIIHHIIIIII",
        40,
        w,
        h * 2,
        1,
        32,
        0,
        len(xor),
        0,
        0,
        0,
        0,
    )
    return header + xor + and_mask


def save_ico(png_path: Path, ico_path: Path) -> None:
    src = _square(Image.open(png_path))
    blobs: list[bytes] = []
    for s in SIZES:
        blobs.append(_dib32(src.resize((s, s), Image.Resampling.LANCZOS)))
    count = len(blobs)
    offset = 6 + 16 * count
    buf = bytearray(struct.pack("<HHH", 0, 1, count))
    for s, blob in zip(SIZES, blobs):
        buf += struct.pack(
            "<BBBBHHII",
            0 if s >= 256 else s,
            0 if s >= 256 else s,
            0,
            0,
            1,
            32,
            len(blob),
            offset,
        )
        offset += len(blob)
    for blob in blobs:
        buf += blob
    ico_path.parent.mkdir(parents=True, exist_ok=True)
    ico_path.write_bytes(bytes(buf))


if __name__ == "__main__":
    if not PNG.exists():
        raise SystemExit(f"找不到 {PNG}")
    save_ico(PNG, ICO)
    print(f"wrote {ICO} ({ICO.stat().st_size} bytes)")
