import contextlib
import io
import os
import subprocess
import tempfile
import unittest

from PIL import Image, ImageDraw

from pdf_watermark.cli import main, parse_color


def make_pdf(path, pages=2, size=(850, 1100)):
    imgs = []
    for i in range(pages):
        img = Image.new("RGB", size, "white")
        ImageDraw.Draw(img).text((50, 50), f"page {i + 1}", fill="black")
        imgs.append(img)
    imgs[0].save(path, save_all=True, append_images=imgs[1:], resolution=100)


def page_count(path):
    out = subprocess.run(["pdfinfo", path], check=True, capture_output=True, text=True).stdout
    return int(next(line for line in out.splitlines() if line.startswith("Pages:")).split()[1])


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


def dominant_tint(path):
    """Average colour of tinted (non-grey) pixels on the first rendered page."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "50", "-png", "-f", "1", "-l", "1", path, f"{tmp}/p"], check=True)
        img = Image.open(next(os.scandir(tmp)).path).convert("RGB")
    pixels = [p for p in img.getdata() if max(p) - min(p) > 30]
    return tuple(sum(c) / len(pixels) for c in zip(*pixels))


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.a = os.path.join(self.dir, "a.pdf")
        self.b = os.path.join(self.dir, "b.pdf")
        make_pdf(self.a, pages=3)
        make_pdf(self.b, pages=1, size=(1100, 850))
        self.out = os.path.join(self.dir, "out")

    def tearDown(self):
        self.tmp.cleanup()

    def test_multiple_files(self):
        code, out, _ = run([self.a, self.b, "-t", "Confidential", "-o", self.out])
        self.assertEqual(code, 0)
        self.assertEqual(page_count(os.path.join(self.out, "a.pdf")), 3)
        self.assertEqual(page_count(os.path.join(self.out, "b.pdf")), 1)
        self.assertIn("ok", out)

    def test_output_has_no_extractable_text(self):
        run([self.a, "-t", "SECRET", "-o", self.out])
        text = subprocess.run(
            ["pdftotext", os.path.join(self.out, "a.pdf"), "-"], capture_output=True, text=True
        ).stdout
        self.assertNotIn("SECRET", text)
        self.assertNotIn("page", text)

    def test_color_flag(self):
        run([self.a, "-t", "X" * 20, "-c", "blue", "--opacity", "0.6", "-o", self.out])
        r, g, b = dominant_tint(os.path.join(self.out, "a.pdf"))
        self.assertGreater(b, r + 40)

        run([self.a, "-t", "X" * 20, "-c", "#00aa00", "--opacity", "0.6", "-o", self.out])
        r, g, b = dominant_tint(os.path.join(self.out, "a.pdf"))
        self.assertGreater(g, r + 40)

    def test_invalid_color(self):
        code, _, err = run([self.a, "-t", "x", "-c", "notacolor", "-o", self.out])
        self.assertEqual(code, 2)
        self.assertIn("invalid color", err)

    def test_missing_text(self):
        code, _, _ = run([self.a])
        self.assertEqual(code, 2)

    def test_bad_input_continues_and_fails(self):
        bad = os.path.join(self.dir, "bad.pdf")
        with open(bad, "w") as f:
            f.write("not a pdf")
        code, out, err = run([bad, self.a, "-t", "x", "-o", self.out])
        self.assertEqual(code, 1)
        self.assertIn("fail", err)
        self.assertTrue(os.path.exists(os.path.join(self.out, "a.pdf")))

    def test_refuses_to_overwrite_input(self):
        code, _, err = run([self.a, "-t", "x", "-o", self.dir])
        self.assertEqual(code, 1)
        self.assertIn("overwrite", err)

    def test_parse_color(self):
        self.assertEqual(parse_color("#ff0000", 0.5), (255, 0, 0, 128))


if __name__ == "__main__":
    unittest.main()
