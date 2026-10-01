"""Candidate papers for a research topic from OpenAlex: semantic search on the description plus keyword searches."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import httpx

API_URL = "https://api.openalex.org/works"
FIELDS = "id,doi,title,publication_date,cited_by_count,primary_location,abstract_inverted_index"
# Semantic search allows 1 request per second; we use the same spacing for every request.
REQUEST_DELAY_S = 1.1
PAGE_SIZE = 100  # documented maximum per page
SEMANTIC_MAX_RESULTS = 50  # semantic search returns at most 50 works
SEMANTIC_MAX_CHARS = 2000  # longer semantic queries are truncated by OpenAlex
KEYWORD_SORTS = ("publication_date:desc", "relevance_score:desc")  # newest matches first, then best of any age


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def title_key(title: str) -> str:
    """Normalized title, to drop the same paper indexed twice (preprint and journal version, duplicates)."""
    return " ".join(re.sub(r"[\W_]+", " ", title.lower()).split())


def abstract_text(inverted: dict[str, list[int]] | None) -> str:
    """OpenAlex stores abstracts as {word: [positions]}; rebuild the plain text."""
    words = {pos: word for word, positions in (inverted or {}).items() for pos in positions}
    return " ".join(words[i] for i in sorted(words))


def parse_work(work: dict) -> dict:
    source = (work.get("primary_location") or {}).get("source") or {}
    return {
        "id": work["id"].rsplit("/", 1)[-1],
        "title": _clean(work.get("title")),
        "abstract": _clean(abstract_text(work.get("abstract_inverted_index"))),
        "published": work.get("publication_date") or "",
        "venue": source.get("display_name"),
        "cited_by_count": work.get("cited_by_count") or 0,
        "url": work.get("doi") or work["id"],
    }


class OpenAlexAPI:
    def __init__(self, client: httpx.Client | None = None, delay_s: float = REQUEST_DELAY_S):
        self.client = client or httpx.Client(timeout=60, headers={"User-Agent": "related-work-finder/0.1"})
        self.delay_s = delay_s
        self._last = 0.0

    def works(self, params: dict, attempts: int = 4) -> tuple[int, list[dict]]:
        """Return (total matches, parsed works). Retries server errors and rate limits, not bad queries."""
        for attempt in range(attempts):
            wait = self._last + self.delay_s - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                resp = self.client.get(API_URL, params={**params, "select": FIELDS})
                resp.raise_for_status()
                data = resp.json()
                return data["meta"]["count"], [parse_work(w) for w in data["results"]]
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if (status < 500 and status != 429) or attempt == attempts - 1:
                    raise RuntimeError(f"OpenAlex HTTP {status}: {exc.response.text[:300]}") from None
            except httpx.HTTPError:
                if attempt == attempts - 1:
                    raise
            time.sleep(self.delay_s * 2 ** (attempt + 1))
        raise AssertionError("unreachable")


def searches(research: str, queries: list[str], per_query: int) -> Iterator[tuple[str, dict, int]]:
    """(label, params, max results) for every search: the description and each query semantically, each query
    as keywords in titles and abstracts, sorted by newest and by relevance."""
    yield "description (semantic)", {"search.semantic": research[:SEMANTIC_MAX_CHARS]}, SEMANTIC_MAX_RESULTS
    for q in queries:
        yield f"{q!r} (semantic)", {"search.semantic": q}, SEMANTIC_MAX_RESULTS
        for sort in KEYWORD_SORTS:
            label = f"{q!r} (keywords, by {sort.split('_')[0]})"
            # Commas separate OpenAlex filters, so they cannot appear inside the search text.
            yield label, {"filter": f"title_and_abstract.search:{q.replace(',', ' ')}", "sort": sort}, per_query


def fetch_candidates(
    out: Path,
    research: str,
    queries: list[str],
    per_query: int = 100,
    api: OpenAlexAPI | None = None,
    log=print,
    today: date | None = None,
) -> int:
    """Append candidates with an abstract to `out` (JSONL), skipping ids and titles already there.

    Each new row records the day it was fetched, so a report can show what is new since the previous fetch.
    """
    api = api or OpenAlexAPI()
    fetched_at = (today or date.today()).isoformat()
    seen_ids, seen_titles = set(), set()
    if out.exists():
        with out.open() as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    seen_ids.add(row["id"])
                    seen_titles.add(title_key(row["title"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with out.open("a") as f:
        for label, params, limit in searches(research, queries, per_query):
            params["filter"] = ",".join(filter(None, [params.get("filter"), "has_abstract:true"]))
            new = total = 0
            for page in range(1, -(-limit // PAGE_SIZE) + 1):
                size = min(PAGE_SIZE, limit - (page - 1) * PAGE_SIZE)
                total, papers = api.works({**params, "per-page": size, "page": page})
                for paper in papers:
                    key = title_key(paper["title"])
                    if paper["id"] in seen_ids or key in seen_titles or not paper["abstract"]:
                        continue
                    seen_ids.add(paper["id"])
                    seen_titles.add(key)
                    f.write(
                        json.dumps({**paper, "found_by": label, "fetched_at": fetched_at}, ensure_ascii=False) + "\n"
                    )
                    new += 1
                if len(papers) < size:
                    break
            f.flush()
            written += new
            log(f"{label}: {new} new ({total} matches)")
    return written
