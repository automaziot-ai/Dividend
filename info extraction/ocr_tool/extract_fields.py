#!/usr/bin/env python3
"""Extract structured fields from a Hebrew pension form PDF using Gemini.

Accepts either a directory of PNG pages or a PDF file (rasterized in-memory).
Outputs JSON with:
  - active_status: "active" | "inactive"
  - client_status: "שכיר" | "עצמאי" | null
  - transfer_to_company: receiving company (from לכבוד at top of transfer form)
  - transfer_to_managing_company: managing company from "פרטי החברה המנהלת" > "שם החברה המנהלת" in the joining form
  - transfer_from_pos: numeric account number of the source fund
"""
import argparse
import io
import json
import os
import sys
from pathlib import Path

import google.generativeai as genai
import fitz  # PyMuPDF


def load_api_key() -> str:
    env_path = Path(__file__).resolve().parent.parent / ".env.ocr"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY missing (set in .env.ocr or env).")
    return key


PROMPT = """You are analyzing scanned images of a Hebrew pension form package.
The package may contain multiple forms including:
  1. "טופס הצטרפות" (Joining form) — has:
       * "פרטי החברה המנהלת" table whose first cell header is "שם החברה המנהלת" (managing company name).
       * "פרטי המעסיק" employer details ("שם המעסיק", etc.).
       * A "מעמד" row with 4 checkboxes (שכיר / שכיר בעל שליטה / עצמאי / עצמאי באמצעות מעסיק).
       * Its main header may indicate the product type, e.g. "טופס הצטרפות לקופת גמל",
         "טופס הצטרפות לקרן פנסיה", "טופס הצטרפות לקרן השתלמות".
  2. "טופס בקשת העברה" (Transfer request form) — its main header ALWAYS includes the product
     type, e.g. "טופס בקשת העברה לקרן פנסיה" / "...לקופת גמל" / "...לקרן השתלמות".
     This form has:
       * A "לכבוד" header at top naming the SOURCE managing company (the firm currently
         holding the money — the one we are transferring FROM).
       * A "פרטי העמית" table with "עמית פעיל"/"עמית לא פעיל" checkboxes.
       * A "פרטי חשבון קופה מעבירה" section containing the source-fund ACCOUNT NUMBER
         (NOT the customer's ID / תעודת זהות).

Extract EXACTLY these 6 fields and return ONLY a JSON object (no markdown, no commentary):

{
  "product": one of "השתלמות", "גמל", "פנסיה", "ייפוי-כח" — determined from the form headers
      ("טופס הצטרפות ל..." or "טופס בקשת העברה ל..."). For a power-of-attorney document (ייפוי כוח)
      return "ייפוי-כח".
  "active_status": "active" or "inactive",
  "client_status": "שכיר" or "עצמאי" (based on which checkbox is marked in מעמד),
  "transfer_to_company": short Hebrew brand name of the RECEIVING company — this is the company
      named in the joining form's "שם החברה המנהלת" (where the money is going TO).
      Examples: "הראל", "מור", "הפניקס", "מיטב", "אלטשולר שחם", "מנורה", "אינטרגמל".
  "transfer_from_company": short Hebrew brand name of the SOURCE company — this is the company
      written after "לכבוד" at the top of the "טופס בקשת העברה" (the firm currently holding the
      money). Same format as transfer_to_company. MUST be different from transfer_to_company
      in a real transfer.
  "transfer_from_pos": the SOURCE-FUND ACCOUNT NUMBER from "פרטי חשבון קופה מעבירה" — typically
      labeled "מספר חשבון" / "חשבון מספר". It is the fund/policy account number, NOT the
      customer's national ID (תעודת זהות, which is 9 digits and matches the עמית's ת.ז.).
      Return as a string of digits.
}

Rules:
- NEVER return the customer's תעודת זהות (national ID) as transfer_from_pos. The customer ID
  appears in "פרטי העמית" labeled "ת.ז." / "מספר זהות" and is NOT the answer.
- For active_status: prefer the "עמית פעיל / לא פעיל" checkboxes. If unclear, infer from
  "שם המעסיק" — non-empty → "active", empty → "inactive".
- For client_status: if either שכיר box is checked return "שכיר"; if either עצמאי box is
  checked return "עצמאי".
- For product: if the package is purely a power-of-attorney (ייפוי כוח / יפוי כח) document
  without joining/transfer forms, return "ייפוי-כח".
- If a field cannot be determined from the images, set its value to null.
- Return ONLY valid JSON, no other text.
"""


def rasterize_pdf(pdf_path: Path, dpi: int = 400) -> list[bytes]:
    doc = fitz.open(pdf_path)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    images = []
    for page in doc:
        pix = page.get_pixmap(matrix=mat, alpha=False)
        images.append(pix.tobytes("png"))
    doc.close()
    return images


def extract(pdf_or_dir: Path, model_name: str, dpi: int) -> dict:
    genai.configure(api_key=load_api_key())
    model = genai.GenerativeModel(model_name)

    if pdf_or_dir.is_dir():
        png_bytes = [p.read_bytes() for p in sorted(pdf_or_dir.glob("*.png"))]
    else:
        png_bytes = rasterize_pdf(pdf_or_dir, dpi=dpi)

    if not png_bytes:
        raise RuntimeError(f"No pages found in {pdf_or_dir}")

    parts = [PROMPT] + [{"mime_type": "image/png", "data": b} for b in png_bytes]
    resp = model.generate_content(
        parts,
        generation_config={"response_mime_type": "application/json"},
    )
    text = (resp.text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text, "_error": "invalid JSON"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path, help="PDF file or directory of PNG pages")
    ap.add_argument("--model", default="gemini-3.5-flash")
    ap.add_argument("--dpi", type=int, default=400)
    args = ap.parse_args()

    if not args.input.exists():
        sys.exit(f"Not found: {args.input}")

    print(f"Processing {args.input.name}...", file=sys.stderr)
    data = extract(args.input, args.model, args.dpi)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
