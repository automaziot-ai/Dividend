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


PROMPT = """You are analyzing scanned images of a Hebrew pension/savings form package.
The package may contain multiple forms including:
  1. "טופס הצטרפות" (Joining form) — has:
       * "פרטי החברה המנהלת" table whose first cell header is "שם החברה המנהלת" (managing company name).
       * "פרטי המעסיק" employer details ("שם המעסיק", etc.).
       * A "מעמד" row with 4 checkboxes (שכיר / שכיר בעל שליטה / עצמאי / עצמאי באמצעות מעסיק).
       * Its main header may indicate the product type, e.g. "טופס הצטרפות לקופת גמל",
         "טופס הצטרפות לקופת גמל להשקעה", "טופס הצטרפות לקרן פנסיה",
         "טופס הצטרפות לקרן השתלמות".
  2. "טופס בקשת העברה" (Transfer request form) — its main header ALWAYS includes the product
     type, e.g. "טופס בקשת העברה לקרן פנסיה" / "...לקופת גמל" / "...לקופת גמל להשקעה" /
     "...לקרן השתלמות". This form has:
       * A "לכבוד" header at top naming the SOURCE managing company (the firm currently
         holding the money — the one we are transferring FROM).
       * A "פרטי העמית" table with "עמית פעיל"/"עמית לא פעיל" checkboxes.
       * A "פרטי חשבון קופה מעבירה" section containing the source-fund ACCOUNT NUMBER
         (NOT the customer's ID / תעודת זהות). May also include the source product type
         (e.g. "גמל", "השתלמות", "פנסיה", "גמל להשקעה").

Product values: "השתלמות", "גמל", "גמל להשקעה", "פנסיה", "ייפוי-כח".
  - "גמל להשקעה" (Gemel LeHashkaa) is a distinct product from regular "גמל". Identify it from
    explicit mentions of "גמל להשקעה" / "קופת גמל להשקעה" in form headers or product fields.
  - If the document only contains a power-of-attorney (ייפוי כוח / יפוי כח), return "ייפוי-כח".

Three extraction modes — choose ONE based on the document content:

MODE A — "גמל להשקעה" product (Gemel LeHashkaa):
  Skip employee/non-employee status and active/inactive status. Extract:
  {
    "product": "גמל להשקעה",
    "transfer_to_company": short Hebrew brand name of the RECEIVING managing company
        (from joining form's "שם החברה המנהלת"),
    "transfer_from_company": short Hebrew brand name of the SOURCE company
        (written after "לכבוד" in "טופס בקשת העברה"),
    "transfer_from_product": the SOURCE product type at the transferring company
        (e.g. "גמל", "השתלמות", "פנסיה", "גמל להשקעה") — taken from the transfer-form
        header or "פרטי חשבון קופה מעבירה" section,
    "transfer_from_pos": SOURCE-FUND ACCOUNT NUMBER from "פרטי חשבון קופה מעבירה"
        ("מספר חשבון" / "חשבון מספר") if it appears in the transfer form. Return as a
        string of digits. If absent from the form, return null.
        NEVER use the customer's national ID (תעודת זהות) here.
    "customer_id": customer's national ID from the JOINING form ("טופס הצטרפות") inside
        the "פרטי העמית" table, cell labeled "מספר זהות/דרכון" (a.k.a. "ת.ז." /
        "מספר זהות"). Return as a string of digits, or null if absent.
    "agent_name": licensed agent's full name from the JOINING form ("טופס הצטרפות")
        inside the "פרטי בעל הרישיון" table — concatenate "שם פרטי" + " " + "שם משפחה".
        Return as a Hebrew string, or null if absent.
    "active_status": null,
    "client_status": null
  }

MODE B — Empty document (no company's own forms / unfilled placeholder):
  The package does NOT include the managing company's own joining/transfer documents
  (e.g. only contains a generic cover sheet, an empty ייפוי כוח, or scanned filler with
  no real form data). Extract only:
  {
    "product": product name if it can be inferred from any header, else null,
    "transfer_to_company": company name if visible anywhere, else null,
    "active_status": null,
    "client_status": null,
    "transfer_from_company": null,
    "transfer_from_product": null,
    "transfer_from_pos": null,
    "customer_id": null,
    "agent_name": null
  }

MODE C — Standard form (default: "גמל" / "השתלמות" / "פנסיה" / "ייפוי-כח"):
  Extract all fields:
  {
    "product": one of "השתלמות", "גמל", "פנסיה", "ייפוי-כח",
    "active_status": "active" or "inactive",
    "client_status": "שכיר" or "עצמאי" (based on the checked מעמד box),
    "transfer_to_company": short Hebrew brand name of the RECEIVING company
        (from joining form's "שם החברה המנהלת").
        Examples: "הראל", "מור", "הפניקס", "מיטב", "אלטשולר שחם", "מנורה", "אינטרגמל".
    "transfer_from_company": short Hebrew brand name of the SOURCE company
        (written after "לכבוד" in "טופס בקשת העברה"). Same format as transfer_to_company.
        MUST differ from transfer_to_company in a real transfer.
    "transfer_from_product": SOURCE product type at the transferring company
        (e.g. "גמל", "השתלמות", "פנסיה", "גמל להשקעה"), or null if not present.
    "transfer_from_pos": SOURCE-FUND ACCOUNT NUMBER from "פרטי חשבון קופה מעבירה" —
        labeled "מספר חשבון" / "חשבון מספר". The fund/policy account number, NOT the
        customer's national ID (תעודת זהות, 9 digits matching the עמית's ת.ז.).
        Return as a string of digits.
    "customer_id": customer's national ID from the JOINING form ("טופס הצטרפות") inside
        the "פרטי העמית" table, cell labeled "מספר זהות/דרכון" (a.k.a. "ת.ז." /
        "מספר זהות"). Return as a string of digits, or null if absent.
    "agent_name": licensed agent's full name from the JOINING form ("טופס הצטרפות")
        inside the "פרטי בעל הרישיון" table — concatenate "שם פרטי" + " " + "שם משפחה".
        Return as a Hebrew string, or null if absent.
  }

Return ONLY a single JSON object (no markdown, no commentary). The object MUST contain
ALL these keys (use null where the chosen mode says to skip a field):
  product, active_status, client_status, transfer_to_company, transfer_from_company,
  transfer_from_product, transfer_from_pos, customer_id, agent_name.

Rules:
- NEVER return the customer's תעודת זהות (national ID) as transfer_from_pos. The customer
  ID appears in "פרטי העמית" labeled "ת.ז." / "מספר זהות" and is NOT the answer.
- CRITICAL: the "מעמד" row (שכיר / עצמאי / שכיר בעל שליטה / עצמאי באמצעות מעסיק) is the
  customer's EMPLOYMENT STATUS — it drives client_status ONLY. It is NEVER evidence for
  active_status. Do NOT infer "active" just because "שכיר" is checked.
- For active_status (Mode C only) — decision priority:
    1) If "טופס בקשת העברה" contains "עמית פעיל / לא פעיל" checkboxes (or
       "עמית פעיל בקופת הגמל המעבירה" / "עמית לא פעיל בקופת הגמל המעבירה"), use them:
         * "פעיל" checked   -> "active"
         * "לא פעיל" checked -> "inactive"
    2) Otherwise, look at "שם המעסיק" in פרטי מעסיק of the joining form:
         non-empty -> "active", empty -> "inactive".
    3) If still undetermined -> null.
- For client_status (Mode C only): if either שכיר box is checked return "שכיר"; if either
  עצמאי box is checked return "עצמאי".
- transfer_from_pos applies in BOTH Mode A and Mode C: if the transfer form
  ("טופס בקשת העברה" / "פרטי חשבון קופה מעבירה") contains an account number labeled
  "מספר חשבון" / "חשבון מספר" / "מספר החשבון בקופת הגמל המעבירה" — return it as a string
  of digits. Otherwise null.
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
