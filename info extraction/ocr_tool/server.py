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
    model = request.values.get("model", DEFAULT_MODEL)
    dpi = int(request.values.get("dpi", DEFAULT_DPI))

    if "file" in request.files:
        f = request.files["file"]
        suffix = Path(f.filename or "upload.pdf").suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            f.save(tmp.name)
            tmp_path = Path(tmp.name)
    elif request.data:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(request.data)
            tmp_path = Path(tmp.name)
    else:
        return jsonify(error="no PDF in request (send multipart 'file' or raw body)"), 400
    try:
        return jsonify(extract(tmp_path, model, dpi))
    except Exception as e:
        return jsonify(error=f"{type(e).__name__}: {e}"), 500
    finally:
        tmp_path.unlink(missing_ok=True)
