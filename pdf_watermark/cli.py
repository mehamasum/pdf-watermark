"""Burn a tiled text watermark into PDFs.

Each page is rendered to an image, the watermark is drawn onto the pixels and
the page is written back as an image. The output has no separate watermark
layer or text object, so it can't be stripped with a PDF editor.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageColor, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
]


def find_font(path=None):
    if path:
        return path
    for candidate in FONT_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    raise SystemExit("error: no usable TrueType font found, pass one with --font")


def parse_color(value, opacity):
    try:
        rgb = ImageColor.getrgb(value)[:3]
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid color: {value!r}")
    return rgb + (round(opacity * 255),)


def watermark_image(img, text, fill, font_path, angle=30):
    img = img.convert("RGBA")
    width, height = img.size
    size = max(width, height) // 45
    font = ImageFont.truetype(font_path, size)

    tile = Image.new("RGBA", (int(font.getlength(text)) + size * 2, size * 2), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((size, size // 2), text, font=font, fill=fill)
    tile = tile.rotate(angle, expand=True)

    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    step_x, step_y = int(tile.width * 0.9), int(tile.height * 0.55)
    for row, y in enumerate(range(-tile.height, height + tile.height, step_y)):
        offset = (row % 2) * step_x // 2
        for x in range(-tile.width + offset, width + tile.width, step_x):
            layer.alpha_composite(tile, (x, y))
    return Image.alpha_composite(img, layer).convert("RGB")


def watermark_pdf(src, dst, text, fill, font_path, dpi=200, quality=80):
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["pdftoppm", "-r", str(dpi), "-png", src, os.path.join(tmp, "p")],
            check=True,
            capture_output=True,
        )
        # pdftoppm zero-pads page numbers to the same width, so a plain sort keeps page order.
        pages = [
            watermark_image(Image.open(p), text, fill, font_path)
            for p in sorted(glob.glob(os.path.join(tmp, "p-*.png")))
        ]
    if not pages:
        raise RuntimeError("no pages rendered")
    pages[0].save(dst, save_all=True, append_images=pages[1:], resolution=dpi, quality=quality)
    return len(pages)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="pdf-watermark",
        description="Burn a non-removable text watermark into one or more PDFs.",
    )
    parser.add_argument("files", nargs="+", metavar="FILE", help="PDF file(s) to watermark")
    parser.add_argument("-t", "--text", required=True, help="watermark text")
    parser.add_argument(
        "-c", "--color", default="red",
        help="watermark color: a name (red, gray) or hex (#c80000). Default: red",
    )
    parser.add_argument(
        "-o", "--output-dir", default="watermarked",
        help="directory for the output PDFs. Default: ./watermarked",
    )
    parser.add_argument(
        "--opacity", type=float, default=0.3,
        help="watermark opacity from 0 to 1. Default: 0.3",
    )
    parser.add_argument("--dpi", type=int, default=200, help="render resolution. Default: 200")
    parser.add_argument("--font", help="path to a TrueType font for the watermark text")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not 0 < args.opacity <= 1:
        parser.error("--opacity must be between 0 and 1")
    try:
        fill = parse_color(args.color, args.opacity)
    except argparse.ArgumentTypeError as e:
        parser.error(str(e))
    if shutil.which("pdftoppm") is None:
        parser.error("pdftoppm not found, install poppler-utils")
    font_path = find_font(args.font)

    os.makedirs(args.output_dir, exist_ok=True)
    failed = 0
    for src in args.files:
        dst = os.path.join(args.output_dir, os.path.basename(src))
        if os.path.abspath(dst) == os.path.abspath(src):
            print(f"skip {src}: output would overwrite the input", file=sys.stderr)
            failed += 1
            continue
        try:
            count = watermark_pdf(src, dst, args.text, fill, font_path, dpi=args.dpi)
        except (subprocess.CalledProcessError, OSError, RuntimeError) as e:
            detail = e.stderr.decode().strip() if getattr(e, "stderr", None) else str(e)
            print(f"fail {src}: {detail}", file=sys.stderr)
            failed += 1
            continue
        print(f"ok   {src} -> {dst} ({count} pages)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
