"""HTTP service wrapping the OCR extractor."""
import os
import tempfile
from pathlib import Path

from flask import Flask, jsonify, request

from extract_fields import extract

app = Flask(__name__)

DEFAULT_MODEL = os.environ.get("OCR_MODEL", "gemini-3.5-flash")
DEFAULT_DPI = int(os.environ.get("OCR_DPI", "400"))


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.post("/extract")
def extract_endpoint():
    if "file" not in request.files:
        return jsonify(error="missing 'file' form field"), 400
    f = request.files["file"]
    model = request.form.get("model", DEFAULT_MODEL)
    dpi = int(request.form.get("dpi", DEFAULT_DPI))

    suffix = Path(f.filename or "upload.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        f.save(tmp.name)
        tmp_path = Path(tmp.name)
    try:
        return jsonify(extract(tmp_path, model, dpi))
    except Exception as e:
        return jsonify(error=f"{type(e).__name__}: {e}"), 500
    finally:
        tmp_path.unlink(missing_ok=True)
