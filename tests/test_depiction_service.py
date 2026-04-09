from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from molquiz.services.depiction import DepictionService


def test_render_png_uses_opaque_white_background(tmp_path: Path) -> None:
    depiction_service = DepictionService(tmp_path / "storage")

    image = Image.open(BytesIO(depiction_service.render_png("COC(=O)CCC(C)C")))
    pixels = list(image.getdata())
    white_pixels = sum(1 for pixel in pixels if pixel == (255, 255, 255))
    dark_pixels = sum(1 for pixel in pixels if min(pixel) < 32)

    assert image.mode == "RGB"
    assert image.getpixel((0, 0)) == (255, 255, 255)
    assert image.getpixel((image.width - 1, image.height - 1)) == (255, 255, 255)
    assert white_pixels > len(pixels) * 0.5
    assert dark_pixels > 1_000
