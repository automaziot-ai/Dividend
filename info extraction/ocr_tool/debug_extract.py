"""Debug-mode extraction: shows OCR text + extraction with reasoning per field."""
import argparse
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import google.generativeai as genai
from extract_fields import load_api_key, rasterize_pdf


OCR_PROMPT = """You are an OCR engine for Hebrew financial/pension forms.

Carefully transcribe ALL Hebrew, English, and numeric text visible in this page image.
Preserve reading order (right-to-left for Hebrew). Preserve table structure as Markdown tables.
For every checkbox indicate whether it is CHECKED (✔) or UNCHECKED (☐) — be precise.
Output ONLY the transcribed content as Markdown. Do not summarize, do not skip boilerplate.
"""


REASONING_PROMPT = """You are analyzing scanned images of a Hebrew pension/savings form package.
Identify the form type(s), extract the same 7 fields as before
(product, active_status, client_status, transfer_to_company, transfer_from_company,
transfer_from_product, transfer_from_pos), AND for EACH field write a short reasoning
sentence (in English) explaining exactly what you saw in the document that led to the
value. Quote any Hebrew labels or values you relied on.

Return ONLY a JSON object of the form:
{
  "fields": {
    "product": "...",
    "active_status": "...",
    "client_status": "...",
    "transfer_to_company": "...",
    "transfer_from_company": "...",
    "transfer_from_product": "...",
    "transfer_from_pos": "..."
  },
  "reasoning": {
    "product": "evidence + decision",
    "active_status": "evidence + decision",
    "client_status": "evidence + decision",
    "transfer_to_company": "evidence + decision",
    "transfer_from_company": "evidence + decision",
    "transfer_from_product": "evidence + decision",
    "transfer_from_pos": "evidence + decision"
  },
  "form_types_found": ["..."]
}

Rules:
- active_status: prefer "עמית פעיל / לא פעיל" checkboxes. If unclear, look at "שם המעסיק"
  (non-empty -> active, empty -> inactive). Explain which one you used.
- Quote the exact text/checkbox state you saw.
"""


def run_ocr(images: list[bytes], model_name: str) -> str:
    model = genai.GenerativeModel(model_name)
    out = []
    for i, b in enumerate(images, 1):
        resp = model.generate_content([OCR_PROMPT, {"mime_type": "image/png", "data": b}])
        try:
            text = resp.text or ""
        except Exception as e:
            text = f"[BLOCKED: {e}]"
        out.append(f"\n\n---\n## page {i}\n\n{text}")
    return "".join(out)


def run_reasoning(images: list[bytes], model_name: str) -> dict:
    model = genai.GenerativeModel(model_name)
    parts = [REASONING_PROMPT] + [{"mime_type": "image/png", "data": b} for b in images]
    resp = model.generate_content(
        parts, generation_config={"response_mime_type": "application/json"}
    )
    text = (resp.text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text, "_error": "invalid JSON"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--model", default="gemini-3.5-flash")
    ap.add_argument("--dpi", type=int, default=400)
    args = ap.parse_args()

    genai.configure(api_key=load_api_key())
    print(f"Rasterizing {args.pdf.name}...", flush=True)
    images = rasterize_pdf(args.pdf, dpi=args.dpi)
    print(f"  {len(images)} page(s)", flush=True)

    print("\n=== OCR ===\n", flush=True)
    ocr_md = run_ocr(images, args.model)
    print(ocr_md)

    print("\n\n=== REASONING ===\n", flush=True)
    data = run_reasoning(images, args.model)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
