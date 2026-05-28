#!/usr/bin/env python3
"""Send rasterized page images to Gemini 2.5 Flash for OCR + structured extraction.

Reads GEMINI_API_KEY from .env.ocr (sibling of the project root) or from the env.
"""
import argparse
import os
import sys
import time
from pathlib import Path

import google.generativeai as genai


def load_api_key() -> str:
    env_path = Path(__file__).resolve().parent.parent / ".env.ocr"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit(
            "GEMINI_API_KEY not found. Create .env.ocr with "
            "GEMINI_API_KEY=... or export it in the environment."
        )
    return key


PROMPT = """You are an OCR engine for Hebrew financial/pension forms.

Carefully transcribe ALL Hebrew, English, and numeric text visible in this page image.
Preserve reading order (right-to-left for Hebrew). Preserve table structure as Markdown tables.
Output ONLY the transcribed content as Markdown. Do not summarize, do not skip boilerplate, do not add commentary.
If a field is filled by hand or has a checkmark, indicate it (e.g., ✔ for checked boxes).
"""


def ocr_pages(pages_dir: Path, out_path: Path, model_name: str) -> None:
    genai.configure(api_key=load_api_key())
    model = genai.GenerativeModel(model_name)

    png_files = sorted(pages_dir.glob("*.png"))
    if not png_files:
        sys.exit(f"No PNGs in {pages_dir}")

    all_md = []
    for png in png_files:
        print(f"OCRing {png.name}...", flush=True)
        img_bytes = png.read_bytes()
        text = ""
        for attempt in range(4):
            try:
                resp = model.generate_content(
                    [PROMPT, {"mime_type": "image/png", "data": img_bytes}]
                )
                try:
                    text = resp.text or ""
                    break
                except Exception:
                    # finish_reason != STOP (e.g., RECITATION). Retry with safer prompt.
                    alt_prompt = (
                        "Describe and transcribe every visible word, number, and checkbox "
                        "in this scanned Hebrew pension form image. Output as Markdown."
                    )
                    resp = model.generate_content(
                        [alt_prompt, {"mime_type": "image/png", "data": img_bytes}]
                    )
                    try:
                        text = resp.text or ""
                        break
                    except Exception as e2:
                        text = f"[BLOCKED on {png.name}: {e2}]"
                        break
            except Exception as e:
                msg = str(e)
                if "429" in msg or "quota" in msg.lower():
                    wait = 15 * (attempt + 1)
                    print(f"  rate-limited, waiting {wait}s...", flush=True)
                    time.sleep(wait)
                    continue
                text = f"[ERROR on {png.name}: {e}]"
                break
        all_md.append(f"\n\n---\n\n## {png.stem}\n\n{text}")
        time.sleep(4)  # throttle to stay under free-tier RPM

    out_path.write_text("".join(all_md), encoding="utf-8")
    print(f"\nWrote: {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pages_dir", type=Path, help="Directory with page-NNN.png images")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--model", default="gemini-3.5-flash")
    args = ap.parse_args()

    if not args.pages_dir.is_dir():
        sys.exit(f"Not a directory: {args.pages_dir}")
    out = args.out or args.pages_dir.parent / (args.pages_dir.name + "_ocr.md")
    ocr_pages(args.pages_dir, out, args.model)


if __name__ == "__main__":
    main()
