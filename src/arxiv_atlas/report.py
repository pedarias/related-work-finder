"""Ranked related-work list from judged candidates: most related first, newest first within each relevance band."""

from __future__ import annotations

import csv
import math
from pathlib import Path

from .classify import read_jsonl
from .questions import PACK_VERSION, topic_key

SECTIONS = {
    "same_problem": "Same problem",
    "same_method": "Same method, different problem",
    "resource": "Datasets, benchmarks, and tools",
    "background": "Background and surveys",
}
BASELINE_P = 0.5
# Relevance scores cluster between 2 and 3.5, so whole levels would order almost everything by date alone.
BAND = 0.5
MOST_CITED = 10


def rank(papers_path: Path, results_path: Path, research: str, min_relevance: float = 2.0) -> tuple[list[dict], int]:
    """Return (papers at or above `min_relevance`, number judged) for this research description and pack.

    Papers from the latest fetch are marked `is_new` once there has been more than one fetch.
    """
    papers = {p["id"]: p for p in read_jsonl(papers_path)}
    fetches = {p.get("fetched_at", "") for p in papers.values()}
    latest = max(fetches) if len(fetches) > 1 else None
    topic = topic_key(research)
    judged = {}
    for row in read_jsonl(results_path):
        if row.get("pack") == PACK_VERSION and row.get("topic") == topic and row["id"] in papers:
            answers = row["answers"]
            judged[row["id"]] = {
                **papers[row["id"]],
                "relevance": answers["relevance"]["score"],
                "relation": answers["relation"]["choice"],
                "baseline": answers["baseline"]["noul"],
                "is_new": papers[row["id"]].get("fetched_at", "") == latest,
            }
    ranked = [p for p in judged.values() if p["relevance"] >= min_relevance]
    ranked.sort(key=lambda p: (math.floor(p["relevance"] / BAND), p["published"]), reverse=True)
    return ranked, len(judged)


def _line(p: dict) -> str:
    venue = f" · {p['venue']}" if p.get("venue") else ""
    return (
        f"- **{p['relevance']:.1f}** · {p['published'][:4]} · {p['cited_by_count']} citations · "
        f"[{p['title']}]({p['url']}){venue}"
    )


def render(ranked: list[dict], judged: int, research: str, min_relevance: float) -> str:
    quoted = "\n".join(f"> {line}" for line in research.strip().splitlines())
    out = [
        "# Related work",
        "",
        quoted,
        "",
        f"{len(ranked)} of {judged} candidates scored relevance ≥ {min_relevance:g} (0–4). "
        f"Most related first; newest first within each {BAND:g}-point band. Citation counts come from OpenAlex.",
    ]
    most_cited = sorted(ranked, key=lambda p: p["cited_by_count"], reverse=True)[:MOST_CITED]
    groups = [
        ("New since the previous fetch", [p for p in ranked if p["is_new"]]),
        ("Most cited", most_cited),
        ("Competing approaches to compare against", [p for p in ranked if p["baseline"] >= BASELINE_P]),
    ]
    groups += [(title, [p for p in ranked if p["relation"] == key]) for key, title in SECTIONS.items()]
    groups.append(("Other", [p for p in ranked if p["relation"] not in SECTIONS]))
    for title, items in groups:
        if items:
            out += ["", f"## {title} ({len(items)})", "", *map(_line, items)]
    return "\n".join(out) + "\n"


def write_csv(ranked: list[dict], path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "published", "relevance", "relation", "baseline", "cited_by_count", "venue", "title", "url"])
        for p in ranked:
            w.writerow(
                [
                    p["id"],
                    p["published"][:10],
                    round(p["relevance"], 2),
                    p["relation"],
                    round(p["baseline"], 2),
                    p["cited_by_count"],
                    p.get("venue") or "",
                    p["title"],
                    p["url"],
                ]
            )
