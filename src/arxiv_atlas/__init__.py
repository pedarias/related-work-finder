"""arxiv-atlas: find the related work for your research, judged by a decision model."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

DATA = Path("data")
RESEARCH_FILE = "research.txt"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="arxiv-atlas")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def topic_parser(name: str, summary: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=summary)
        p.add_argument("topic", help=f"folder under data/ that holds {RESEARCH_FILE} and all outputs")
        return p

    p = topic_parser("fetch", "candidate papers from OpenAlex: semantic and keyword searches (re-runs add only new)")
    p.add_argument(
        "--query",
        action="append",
        default=[],
        help="a short phrase, e.g. 'road weather classification'; searched semantically and as keywords; repeatable",
    )
    p.add_argument("--per-query", type=int, default=100, help="keyword results per query and sort order")

    p = topic_parser("estimate", "pre-flight token/cost/time estimate (no API calls)")
    p.add_argument("--rpm", type=float, default=1000)

    p = topic_parser("classify", "judge candidates against your research with Jev (resumable, needs TYPESAFE_API_KEY)")
    p.add_argument("--model", default="jev-1.13.0")
    p.add_argument("--rpm", type=float, default=1000, help="stay below the 1,200 rpm account limit")
    p.add_argument("--concurrency", type=int, default=32)
    p.add_argument("--limit", type=int, help="judge at most N new papers")
    p.add_argument("--max-cost", type=float, required=True, help="stop once this many USD have been spent")

    p = topic_parser("report", "ranked related-work list (report.md, ranked.csv)")
    p.add_argument("--min-relevance", type=float, default=2.0, help="0 unrelated … 4 same problem")

    args = parser.parse_args(argv)
    folder = DATA / args.topic
    candidates, judged = folder / "candidates.jsonl", folder / "judged.jsonl"

    def research() -> str:
        path = folder / RESEARCH_FILE
        text = path.read_text().strip() if path.exists() else ""
        if not text:
            parser.error(f"write a few sentences about your research in {path} first")
        return text

    if args.cmd == "fetch":
        from .fetch import fetch_candidates

        n = fetch_candidates(candidates, research(), args.query, args.per_query)
        print(f"wrote {n} new candidates to {candidates}")
    elif args.cmd == "estimate":
        from .classify import estimate

        print(json.dumps(estimate(candidates, research(), args.rpm), indent=2))
    elif args.cmd == "classify":
        from .classify import JevBackend, classify

        text = research()
        if not os.environ.get("TYPESAFE_API_KEY", "").strip():
            parser.error("TYPESAFE_API_KEY is not set; export it in your shell (console.typesafe.ai/settings/keys)")

        async def run() -> dict:
            async with JevBackend(args.model) as backend:
                return await classify(
                    candidates,
                    judged,
                    backend,
                    text,
                    rpm=args.rpm,
                    concurrency=args.concurrency,
                    limit=args.limit,
                    max_cost_usd=args.max_cost,
                )

        print(json.dumps(asyncio.run(run()), indent=2))
    elif args.cmd == "report":
        from .report import rank, render, write_csv

        text = research()
        ranked, n_judged = rank(candidates, judged, text, args.min_relevance)
        if not n_judged:
            parser.error(f"no papers judged for the current {RESEARCH_FILE} yet; run `classify {args.topic}` first")
        (folder / "report.md").write_text(render(ranked, n_judged, text, args.min_relevance))
        write_csv(ranked, folder / "ranked.csv")
        print(f"{len(ranked)} of {n_judged} judged papers kept; wrote", folder / "report.md", folder / "ranked.csv")
