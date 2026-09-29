"""arxiv-atlas: decades of arXiv abstracts, read by a decision model."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import date
from pathlib import Path

DATA = Path("data")


def _last_full_month() -> str:
    today = date.today()
    y, m = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    return f"{y:04d}{m:02d}"


def main(argv: list[str] | None = None) -> None:
    from .questions import PACK_VERSION

    parser = argparse.ArgumentParser(prog="arxiv-atlas")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("fetch", help="stratified pilot sample from the arXiv API (resumable)")
    p.add_argument("--out", type=Path, default=DATA / "raw" / "pilot.jsonl")
    p.add_argument("--category", default="cs.*")
    p.add_argument("--start", default="199801", help="first month, YYYYMM")
    p.add_argument("--end", default=_last_full_month(), help="last month, YYYYMM")
    p.add_argument("--per-month", type=int, default=30)
    p.add_argument("--seed", type=int, default=42)

    p = sub.add_parser("estimate", help="pre-flight token/cost/time estimate (no API calls)")
    p.add_argument("--papers", type=Path, default=DATA / "raw" / "pilot.jsonl")
    p.add_argument("--rpm", type=float, default=1000)

    p = sub.add_parser("classify", help="run Jev over papers (resumable, needs TYPESAFE_API_KEY)")
    p.add_argument("--papers", type=Path, default=DATA / "raw" / "pilot.jsonl")
    p.add_argument("--out", type=Path, default=DATA / "results" / f"pilot.{PACK_VERSION}.jsonl")
    p.add_argument("--model", default="jev-1.13.0")
    p.add_argument("--rpm", type=float, default=1000, help="stay below the 1,200 rpm account limit")
    p.add_argument("--concurrency", type=int, default=32)
    p.add_argument("--limit", type=int, help="classify at most N new papers")
    p.add_argument("--max-cost", type=float, required=True, help="stop once this many USD have been spent")

    p = sub.add_parser("analyze", help="yearly aggregates, sanity checks, charts")
    p.add_argument("--papers", type=Path, default=DATA / "raw" / "pilot.jsonl")
    p.add_argument("--results", type=Path, default=DATA / "results" / f"pilot.{PACK_VERSION}.jsonl")
    p.add_argument("--out-dir", type=Path, default=Path("reports"))

    args = parser.parse_args(argv)

    if args.cmd == "fetch":
        from .fetch import fetch_sample

        n = fetch_sample(args.out, args.category, args.start, args.end, args.per_month, args.seed)
        print(f"wrote {n} papers to {args.out}")
    elif args.cmd == "estimate":
        from .classify import estimate

        print(json.dumps(estimate(args.papers, args.rpm), indent=2))
    elif args.cmd == "classify":
        from .classify import JevBackend, classify

        if not os.environ.get("TYPESAFE_API_KEY", "").strip():
            parser.error("TYPESAFE_API_KEY is not set; export it in your shell (console.typesafe.ai/settings/keys)")

        async def run() -> dict:
            async with JevBackend(args.model) as backend:
                return await classify(
                    args.papers,
                    args.out,
                    backend,
                    rpm=args.rpm,
                    concurrency=args.concurrency,
                    limit=args.limit,
                    max_cost_usd=args.max_cost,
                )

        print(json.dumps(asyncio.run(run()), indent=2))
    elif args.cmd == "analyze":
        from .analyze import charts, checks, load, yearly

        con = load(args.papers, args.results, PACK_VERSION)
        df = yearly(con)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.out_dir / "yearly.csv", index=False)
        report = checks(con)
        (args.out_dir / "checks.json").write_text(json.dumps(report, indent=2, default=str))
        paths = charts(df, args.out_dir)
        print(json.dumps(report, indent=2, default=str))
        print("wrote", args.out_dir / "yearly.csv", *paths)
