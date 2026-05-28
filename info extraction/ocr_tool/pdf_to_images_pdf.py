#!/usr/bin/env python3
"""Rasterize a PDF to high-DPI images, then rebuild a single PDF from those images.

Usage:
    python pdf_to_images_pdf.py <input.pdf> [--dpi 400] [--out <out.pdf>] [--keep-pngs]
"""
import argparse
import sys
from pathlib import Path

import fitz  # PyMuPDF


def rasterize_pdf(input_path: Path, dpi: int, out_pdf: Path, keep_pngs: bool) -> None:
    src = fitz.open(input_path)
    png_dir = out_pdf.with_suffix("").parent / (out_pdf.stem + "_pages")
    png_dir.mkdir(parents=True, exist_ok=True)

    new_pdf = fitz.open()
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    for i, page in enumerate(src, start=1):
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        png_path = png_dir / f"page-{i:03d}.png"
        pix.save(png_path)
        print(f"  page {i}: {pix.width}x{pix.height} -> {png_path.name}")

        rect = fitz.Rect(0, 0, pix.width, pix.height)
        new_page = new_pdf.new_page(width=pix.width, height=pix.height)
        new_page.insert_image(rect, filename=str(png_path))

    new_pdf.save(out_pdf, deflate=True)
    new_pdf.close()
    src.close()

    print(f"\nWrote: {out_pdf}")
    print(f"Pages dir: {png_dir}")
    if not keep_pngs:
        for p in png_dir.glob("*.png"):
            p.unlink()
        png_dir.rmdir()
        print("(cleaned up PNGs; pass --keep-pngs to retain them)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("--dpi", type=int, default=400)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--keep-pngs", action="store_true")
    args = ap.parse_args()

    if not args.input.exists():
        sys.exit(f"Input not found: {args.input}")

    out = args.out or args.input.with_name(args.input.stem + f"_rasterized_{args.dpi}dpi.pdf")
    print(f"Rasterizing {args.input.name} at {args.dpi} DPI...")
    rasterize_pdf(args.input, args.dpi, out, keep_pngs=True)  # keep pngs for OCR step
    if not args.keep_pngs:
        # actually keep them — they're needed for the OCR step
        pass


if __name__ == "__main__":
    main()
