"""Rebuild the README examples.

Writes examples/sample.pdf (a fake 3-page document), a watermarked copy per
variant in examples/output/ and a page-1 preview of each in examples/previews/.

Run from the repo root: python3 -m examples.build
"""
import os
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont

from pdf_watermark.cli import find_font, main as watermark

HERE = os.path.dirname(os.path.abspath(__file__))
LINE = "The quick brown fox jumps over the lazy dog. 0123456789"

VARIANTS = {
    "red": ["-t", "Confidential. For the eyes of Jane Doe"],
    "navy": ["-t", "Confidential. For the eyes of Jane Doe", "-c", "navy"],
    "green": ["-t", "Confidential. For the eyes of Jane Doe", "-c", "#1a7f37"],
    "gray-draft": ["-t", "DRAFT - DO NOT SHARE", "-c", "gray", "--opacity", "0.5"],
}


def page(title, size):
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    draw.text((60, 50), title, font=ImageFont.truetype(find_font(), 36), fill="black")
    body = ImageFont.truetype(find_font(), 16)
    for i, y in enumerate(range(130, size[1] - 160, 28)):
        draw.text((60, y), f"{i + 1:02d}. {LINE}", font=body, fill=(40, 40, 40))
    draw.rectangle((60, size[1] - 130, 360, size[1] - 60), outline="black", width=2)
    draw.text((75, size[1] - 105), "Signature / Stamp", font=body, fill="black")
    return img


def make_sample(path):
    pages = [
        page("Sample Agreement - Page 1", (827, 1169)),
        page("Sample Agreement - Page 2", (827, 1169)),
        page("Annex A - Landscape page", (1169, 827)),
    ]
    pages[0].save(path, save_all=True, append_images=pages[1:], resolution=100)


def preview(pdf, jpg):
    stem = jpg[: -len(".jpg")]
    subprocess.run(
        ["pdftoppm", "-r", "60", "-jpeg", "-jpegopt", "quality=85", "-singlefile", "-f", "1", "-l", "1", pdf, stem],
        check=True,
    )


def main():
    out_dir = os.path.join(HERE, "output")
    preview_dir = os.path.join(HERE, "previews")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(preview_dir, exist_ok=True)

    sample = os.path.join(HERE, "sample.pdf")
    make_sample(sample)
    preview(sample, os.path.join(preview_dir, "original.jpg"))

    tmp = os.path.join(out_dir, ".tmp")
    for name, args in VARIANTS.items():
        if watermark([sample, *args, "--dpi", "100", "-o", tmp]) != 0:
            raise SystemExit(f"failed to build {name}")
        dst = os.path.join(out_dir, f"{name}.pdf")
        os.replace(os.path.join(tmp, "sample.pdf"), dst)
        preview(dst, os.path.join(preview_dir, f"{name}.jpg"))
    shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
