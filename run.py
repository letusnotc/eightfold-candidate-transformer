#!/usr/bin/env python3
"""
Eightfold Candidate Transformer — CLI

Usage:
  python run.py --csv samples/sample_candidates.csv --github priyasharma
  python run.py --csv samples/sample_candidates.csv --resume samples/sample_resume.txt --config configs/custom_config.json
  python run.py --sample    # run on built-in sample data
  python run.py --sample --config configs/custom_config.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s  %(name)s  %(message)s",
        stream=sys.stderr,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Eightfold Candidate Transformer — Multi-source candidate data pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--csv",     metavar="FILE",  help="Path to recruiter CSV file")
    parser.add_argument("--ats",     metavar="FILE",  help="Path to ATS JSON file")
    parser.add_argument("--resume",  metavar="FILE",  help="Path to resume PDF, DOCX, or TXT")
    parser.add_argument("--github",  metavar="USER",  help="GitHub username or profile URL")
    parser.add_argument("--notes",   metavar="FILE",  help="Path to recruiter notes .txt")
    parser.add_argument("--config",  metavar="FILE",  help="Path to output config JSON (optional)")
    parser.add_argument("--output",  metavar="FILE",  help="Output file path (default: stdout)")
    parser.add_argument("--sample",  action="store_true", help="Run on built-in sample data")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    parser.add_argument("--pretty",  action="store_true", default=True, help="Pretty-print JSON output (default: on)")
    parser.add_argument("--compact", action="store_true", help="Compact JSON output (overrides --pretty)")

    args = parser.parse_args()
    setup_logging(args.verbose)

    # Load config
    config: dict = {}
    if args.config:
        try:
            with open(args.config, "r", encoding="utf-8") as f:
                config = json.load(f)
        except FileNotFoundError:
            print(f"✗ Config file not found: {args.config}", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"✗ Invalid JSON in config file: {e}", file=sys.stderr)
            sys.exit(1)

    # Run pipeline
    from pipeline.orchestrator import run_pipeline, run_sample_pipeline_full

    if args.sample:
        print("▶ Running on built-in sample data (all sources)...", file=sys.stderr)
        result = asyncio.run(run_sample_pipeline_full(config=config))
    else:
        if not any([args.csv, args.ats, args.resume, args.github, args.notes]):
            parser.print_help()
            print("\n✗ Please provide at least one input source (--csv, --ats, --resume, --github, --notes, or --sample)",
                  file=sys.stderr)
            sys.exit(1)

        result = asyncio.run(run_pipeline(
            csv_path=args.csv,
            ats_path=args.ats,
            resume_path=args.resume,
            github_url=args.github,
            notes_path=args.notes,
            config=config,
        ))

    # Report pipeline errors to stderr
    if result.get("pipeline_errors"):
        for err in result["pipeline_errors"]:
            print(f"⚠  {err}", file=sys.stderr)

    if result.get("validation_errors"):
        print("Validation errors:", file=sys.stderr)
        for err in result["validation_errors"]:
            print(f"  ✗ {err}", file=sys.stderr)

    # Format output
    indent = None if args.compact else 2
    output_json = json.dumps(result, indent=indent, ensure_ascii=False, default=str)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_json)
            sources = ", ".join(result.get("sources_used", []))
            print(f"✓ Output written to {args.output}  (sources: {sources})", file=sys.stderr)
        except IOError as e:
            print(f"✗ Failed to write output: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
