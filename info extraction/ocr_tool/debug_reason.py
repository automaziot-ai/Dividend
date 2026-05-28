"""Reasoning-only debug: rasterize PDF, ask Gemini for fields + reasoning."""
import argparse
import io
import json
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import google.generativeai as genai
from extract_fields import load_api_key, rasterize_pdf


REASONING_PROMPT = """You are analyzing scanned images of a Hebrew pension/savings form package.
Extract these 7 fields and for EACH field write a short reasoning sentence (in English)
that quotes the exact Hebrew label/value/checkbox state you relied on.

Fields:
  product, active_status, client_status, transfer_to_company, transfer_from_company,
  transfer_from_product, transfer_from_pos

Important distinctions:
- "מעמד" checkbox (שכיר / עצמאי) is the EMPLOYMENT STATUS — drives client_status, NOT active_status.
- active_status comes from "עמית פעיל / לא פעיל" checkboxes on the transfer form ("טופס בקשת העברה"),
  OR if missing, from "שם המעסיק": non-empty -> "active", empty -> "inactive".
- "לא פעיל" checked -> "inactive"; "פעיל" checked -> "active".

Return ONLY a JSON object:
{
  "fields": {
    "product": "...", "active_status": "...", "client_status": "...",
    "transfer_to_company": "...", "transfer_from_company": "...",
    "transfer_from_product": "...", "transfer_from_pos": "..."
  },
  "reasoning": {
    "product": "...", "active_status": "...", "client_status": "...",
    "transfer_to_company": "...", "transfer_from_company": "...",
    "transfer_from_product": "...", "transfer_from_pos": "..."
  },
  "form_types_found": ["..."]
}
"""


def run(pdf: Path, model_name: str, dpi: int) -> dict:
    genai.configure(api_key=load_api_key())
    images = rasterize_pdf(pdf, dpi=dpi)
    print(f"  {len(images)} page(s)", flush=True)
    model = genai.GenerativeModel(model_name)
    parts = [REASONING_PROMPT] + [{"mime_type": "image/png", "data": b} for b in images]
    for attempt in range(3):
        try:
            resp = model.generate_content(
                parts, generation_config={"response_mime_type": "application/json"}
            )
            text = (resp.text or "").strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"_raw": text, "_error": "invalid JSON"}
        except Exception as e:
            print(f"  attempt {attempt + 1} failed: {e}", flush=True)
            time.sleep(15 * (attempt + 1))
    raise RuntimeError("all attempts failed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--model", default="gemini-3.5-flash")
    ap.add_argument("--dpi", type=int, default=400)
    args = ap.parse_args()
    print(f"Rasterizing {args.pdf.name}...", flush=True)
    data = run(args.pdf, args.model, args.dpi)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
