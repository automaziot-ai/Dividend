"""Batch runner: extract all PDFs in a folder, save JSON."""
import argparse
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from extract_fields import extract


def run(folder: Path, out_path: Path, model: str, dpi: int) -> None:
    pdfs = sorted(p for p in folder.glob("*.pdf") if "_rasterized_" not in p.name)
    print(f"Found {len(pdfs)} PDFs in {folder}", flush=True)
    results = {}
    for p in pdfs:
        print(f"=== {p.name} ===", flush=True)
        try:
            data = extract(p, model, dpi)
            results[p.name] = data
            print(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            results[p.name] = {"_error": f"{type(e).__name__}: {e}"}
            print(f"ERROR: {type(e).__name__}: {e}")
        print()
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved -> {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--model", default="gemini-3.5-flash")
    ap.add_argument("--dpi", type=int, default=400)
    args = ap.parse_args()
    out = args.out or Path(f"extraction_results_{args.folder.name}.json")
    run(args.folder, out, args.model, args.dpi)


if __name__ == "__main__":
    main()
