#!/usr/bin/env python3
"""Translate a document from the command line (no HTTP server needed)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import env_defaults
from backend.app.model import FakeAdapter, LlamaCppAdapter
from backend.app.pipeline import translate_document
from backend.app.translate.glossary import parse_glossary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--out")
    parser.add_argument("--to", default="zh-CN")
    parser.add_argument("--from", dest="source", default="auto")
    parser.add_argument("--style", default="natural")
    parser.add_argument("--domain", default="general")
    parser.add_argument("--glossary", help="file with lines: source => target")
    parser.add_argument("--fake", action="store_true", help="use the deterministic fake model")
    parser.add_argument("--report", help="write quality report to this path")
    args = parser.parse_args()

    source = Path(args.input)
    if not source.exists():
        raise SystemExit("input not found: " + str(source))
    out = Path(args.out) if args.out else source.with_name(source.stem + "." + args.to + source.suffix)

    settings = env_defaults()
    glossary = []
    if args.glossary:
        glossary = parse_glossary(Path(args.glossary).read_text(encoding="utf-8"))

    use_fake = args.fake or os.environ.get("MODEL_BACKEND", "").lower() == "fake"
    model = FakeAdapter(settings) if use_fake else LlamaCppAdapter(settings)

    def progress(stage: str, percent: int, done: int, total: int) -> None:
        print("[" + stage + "] " + str(percent) + "% " + str(done) + "/" + str(total), file=sys.stderr)

    try:
        report = translate_document(
            source,
            out,
            settings=settings,
            model=model,
            source_lang=args.source,
            target_lang=args.to,
            style=args.style,
            domain=args.domain,
            glossary=glossary,
            progress=progress,
        )
    finally:
        model.close()

    report_path = Path(args.report) if args.report else out.with_name(out.stem + ".report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "output": str(out),
        "report": str(report_path),
        "units": report["units"],
        "translated": report["translated"],
        "failed": len(report["failed"]),
        "hard_checks_ok": report["hard_checks_ok"],
        "duration_seconds": report["duration_seconds"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
