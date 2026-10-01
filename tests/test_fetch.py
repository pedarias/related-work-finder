import json
from datetime import date

import httpx
import pytest

from arxiv_atlas.fetch import OpenAlexAPI, abstract_text, fetch_candidates, parse_work, title_key

WORK = {
    "id": "https://openalex.org/W4315647870",
    "doi": "https://doi.org/10.3390/s23020798",
    "title": "Deep Learning with  Attention Mechanisms\nfor Road Weather Detection",
    "publication_date": "2023-01-10",
    "cited_by_count": 31,
    "primary_location": {"source": {"display_name": "Sensors"}},
    "abstract_inverted_index": {"There": [0], "is": [1, 3], "great": [2], "more": [4]},
}


def test_abstract_text_rebuilds_word_order():
    assert abstract_text(WORK["abstract_inverted_index"]) == "There is great is more"
    assert abstract_text(None) == ""


def test_parse_work_normalizes_fields():
    assert parse_work(WORK) == {
        "id": "W4315647870",
        "title": "Deep Learning with Attention Mechanisms for Road Weather Detection",
        "abstract": "There is great is more",
        "published": "2023-01-10",
        "venue": "Sensors",
        "cited_by_count": 31,
        "url": "https://doi.org/10.3390/s23020798",
    }


def test_parse_work_without_doi_or_source():
    paper = parse_work({"id": "https://openalex.org/W1", "title": None, "primary_location": None})
    assert paper["url"] == "https://openalex.org/W1" and paper["venue"] is None and paper["title"] == ""


def test_title_key_ignores_case_and_punctuation():
    assert title_key("A CNN–RNN Architecture for Multi-Label Weather Recognition") == title_key(
        "A CNN-RNN architecture for multi-label weather recognition"
    )
    # Non-Latin titles must keep their letters, or they would all collapse to the same key.
    assert title_key("도로기상요인의 영향") == "도로기상요인의 영향" and title_key("Visão Térmica!") == "visão térmica"


def test_bad_query_is_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400, json={"error": "Invalid query parameters error."})

    api = OpenAlexAPI(httpx.Client(transport=httpx.MockTransport(handler)), delay_s=0)
    with pytest.raises(RuntimeError, match="HTTP 400.*Invalid query"):
        api.works({"search.semantic": "x"})
    assert len(calls) == 1


def test_works_sends_select_and_parses():
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return httpx.Response(200, json={"meta": {"count": 7}, "results": [WORK]})

    api = OpenAlexAPI(httpx.Client(transport=httpx.MockTransport(handler)), delay_s=0)
    total, papers = api.works({"search.semantic": "road weather"})
    assert total == 7 and papers[0]["id"] == "W4315647870"
    assert seen["search.semantic"] == "road weather" and "abstract_inverted_index" in seen["select"]


class FakeAPI:
    """Returns `total` papers p0..p{total-1}, paged; every search returns the same ids."""

    def __init__(self, total):
        self.total, self.calls = total, []

    def works(self, params):
        self.calls.append(params)
        start = (params["page"] - 1) * 100
        n = max(0, min(params["per-page"], self.total - start))
        papers = [{"id": f"p{start + i}", "title": f"Paper {start + i}", "abstract": "a"} for i in range(n)]
        return self.total, papers


def test_fetch_candidates_runs_every_search_and_dedupes(tmp_path):
    out, api = tmp_path / "candidates.jsonl", FakeAPI(total=150)
    n = fetch_candidates(
        out,
        "My research.",
        ["road weather, scene"],
        per_query=200,
        api=api,
        log=lambda *_: None,
        today=date(2026, 9, 30),
    )
    assert n == 150
    assert [(c.get("search.semantic"), c.get("sort"), c["page"], c["per-page"]) for c in api.calls] == [
        ("My research.", None, 1, 50),
        ("road weather, scene", None, 1, 50),
        (None, "publication_date:desc", 1, 100),
        (None, "publication_date:desc", 2, 100),
        (None, "relevance_score:desc", 1, 100),
        (None, "relevance_score:desc", 2, 100),
    ]
    assert all(c["filter"].endswith("has_abstract:true") for c in api.calls)
    assert api.calls[2]["filter"] == "title_and_abstract.search:road weather  scene,has_abstract:true"
    rows = [json.loads(line) for line in out.open()]
    assert len(rows) == 150 and rows[0]["found_by"] == "description (semantic)"
    assert {r["fetched_at"] for r in rows} == {"2026-09-30"}
    assert rows[50]["found_by"] == "'road weather, scene' (keywords, by publication)"


def test_fetch_candidates_skips_known_ids_titles_and_empty_abstracts(tmp_path):
    out = tmp_path / "candidates.jsonl"
    out.write_text(json.dumps({"id": "other", "title": "PAPER 3!"}) + "\n")

    class Mixed(FakeAPI):
        def works(self, params):
            total, papers = super().works(params)
            return total, papers + [{"id": "no-abstract", "title": "No abstract", "abstract": ""}]

    n = fetch_candidates(out, "My research.", [], api=Mixed(total=10), log=lambda *_: None)
    assert n == 9  # p0..p9 minus "Paper 3", which is already there under another id
    assert len(out.read_text().splitlines()) == 10
