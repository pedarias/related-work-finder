"""Stratified pilot sample from the arXiv API: a random contiguous slice of papers per month."""

from __future__ import annotations

import calendar
import json
import random
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import httpx

API_URL = "https://export.arxiv.org/api/query"
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}
# arXiv asks API clients to wait 3 seconds between requests.
REQUEST_DELAY_S = 3.1
_ID_RE = re.compile(r"arxiv\.org/abs/(?P<id>.+?)(?P<version>v\d+)?$")


def months(start: str, end: str) -> Iterator[str]:
    """Yield YYYYMM strings from start to end inclusive."""
    y, m = int(start[:4]), int(start[4:])
    ey, em = int(end[:4]), int(end[4:])
    while (y, m) <= (ey, em):
        yield f"{y:04d}{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def parse_feed(xml_text: str) -> tuple[int, list[dict]]:
    """Return (totalResults, entries) from an arXiv Atom feed. Raises on API error entries."""
    root = ET.fromstring(xml_text)
    total = int(root.findtext("opensearch:totalResults", "0", NS))
    papers = []
    for entry in root.findall("atom:entry", NS):
        raw_id = entry.findtext("atom:id", "", NS)
        if raw_id.endswith("/api/errors"):
            raise RuntimeError(f"arXiv API error: {_clean(entry.findtext('atom:summary', '', NS))}")
        match = _ID_RE.search(raw_id)
        primary = entry.find("arxiv:primary_category", NS)
        papers.append(
            {
                "id": match["id"] if match else raw_id,
                "version": (match["version"] if match else None) or "v1",
                "title": _clean(entry.findtext("atom:title", "", NS)),
                "abstract": _clean(entry.findtext("atom:summary", "", NS)),
                "published": entry.findtext("atom:published", "", NS),
                "primary_category": primary.get("term") if primary is not None else None,
                "categories": [c.get("term") for c in entry.findall("atom:category", NS)],
                "comment": _clean(entry.findtext("arxiv:comment", "", NS)) or None,
            }
        )
    return total, papers


class ArxivAPI:
    def __init__(self, client: httpx.Client | None = None, delay_s: float = REQUEST_DELAY_S):
        self.client = client or httpx.Client(timeout=60, headers={"User-Agent": "arxiv-atlas/0.1"})
        self.delay_s = delay_s
        self._last = 0.0

    def query(self, search_query: str, start: int, max_results: int, attempts: int = 4) -> tuple[int, list[dict]]:
        for attempt in range(attempts):
            wait = self._last + self.delay_s - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                resp = self.client.get(
                    API_URL,
                    params={"search_query": search_query, "start": start, "max_results": max_results},
                )
                resp.raise_for_status()
                return parse_feed(resp.text)
            except (httpx.HTTPError, RuntimeError, ET.ParseError):
                if attempt == attempts - 1:
                    raise
                time.sleep(self.delay_s * 2 ** (attempt + 1))
        raise AssertionError("unreachable")


def month_query(category: str, month: str) -> str:
    last_day = calendar.monthrange(int(month[:4]), int(month[4:]))[1]
    return f"cat:{category} AND submittedDate:[{month}010000 TO {month}{last_day:02d}2359]"


def sample_month(
    api: ArxivAPI, category: str, month: str, per_month: int, rng: random.Random, total_hint: int | None
) -> tuple[int, list[dict]]:
    """Fetch a random contiguous slice of `per_month` papers submitted in `month`. Returns (total, papers).

    `total_hint` (usually the previous month's total) lets us pick the offset without a separate count
    request; if the guess overshoots, the response reports the real total and we retry once.
    """
    query = month_query(category, month)
    if total_hint is None:
        total_hint, _ = api.query(query, 0, 1)
    offset = rng.randint(0, max(0, total_hint - per_month))
    total, papers = api.query(query, offset, per_month)
    if not papers and total > 0:
        offset = rng.randint(0, max(0, total - per_month))
        total, papers = api.query(query, offset, per_month)
    for paper in papers:
        paper["sample_month"] = month
        paper["month_total"] = total
    return total, papers


def fetch_sample(
    out: Path, category: str, start: str, end: str, per_month: int, seed: int, api: ArxivAPI | None = None, log=print
) -> int:
    """Append a stratified sample to `out` (JSONL). Resumable: months already present are skipped."""
    api = api or ArxivAPI()
    done: dict[str, int] = {}
    if out.exists():
        with out.open() as f:
            for line in f:
                row = json.loads(line)
                done[row["sample_month"]] = row["month_total"]
    out.parent.mkdir(parents=True, exist_ok=True)
    written, hint = 0, None
    with out.open("a") as f:
        for month in months(start, end):
            if month in done:
                hint = done[month]
                continue
            hint, papers = sample_month(api, category, month, per_month, random.Random(f"{seed}-{month}"), hint)
            seen = set()
            for paper in papers:
                if paper["id"] not in seen and paper["abstract"]:
                    seen.add(paper["id"])
                    f.write(json.dumps(paper, ensure_ascii=False) + "\n")
            f.flush()
            written += len(seen)
            log(f"{month}: {len(seen)} papers (month total {hint}) — {written} written this run")
    return written
