import json

from conftest import RESEARCH, FakeBackend, fake_response

from related_work_finder.classify import classify
from related_work_finder.report import rank, render, write_csv

# id -> (relevance, relation, baseline probability); papers not listed are unrelated.
JUDGEMENTS = {
    "p1": (3.8, "same_problem", 0.9),  # published 2011
    "p9": (3.6, "same_problem", 0.2),  # published 2019: same band as p1, so it comes first
    "p2": (2.4, "resource", 0.1),
    "p3": (3.1, "unrelated", 0.0),  # published 2013: a higher band than p8, so it comes first despite being older
    "p8": (2.6, "same_problem", 0.1),
    "p4": (1.9, "same_method", 0.8),  # below the default cut-off
}


class JudgingBackend(FakeBackend):
    async def evaluate(self, state):
        response = fake_response(state["title"])
        relevance, relation, baseline = JUDGEMENTS.get(state["title"], (0.2, "unrelated", 0.0))
        response["answers"]["relevance"]["score"] = relevance
        response["answers"]["relation"]["choice"] = relation
        response["answers"]["baseline"]["noul"] = baseline
        return response


async def judge(papers_file, tmp_path, research=RESEARCH):
    results = tmp_path / "judged.jsonl"
    await classify(papers_file, results, JudgingBackend(), research, rpm=60_000, log=lambda *_: None)
    return results


async def test_rank_orders_by_band_then_newest(papers_file, tmp_path):
    ranked, judged = rank(papers_file, await judge(papers_file, tmp_path), RESEARCH)
    assert judged == 20
    assert [p["id"] for p in ranked] == ["p9", "p1", "p3", "p8", "p2"]


async def test_rank_ignores_results_for_other_research(papers_file, tmp_path):
    results = await judge(papers_file, tmp_path)
    assert rank(papers_file, results, "Something else entirely.") == ([], 0)


async def test_report_groups_and_flags_baselines(papers_file, tmp_path):
    ranked, judged = rank(papers_file, await judge(papers_file, tmp_path), RESEARCH)
    md = render(ranked, judged, RESEARCH, 2.0)
    assert md.startswith("# Related work\n\n> We predict molecular properties")
    assert "5 of 20 candidates" in md and "newest first within each 0.5-point band" in md
    sections = [line for line in md.splitlines() if line.startswith("## ")]
    assert sections == [
        "## Most cited (5)",
        "## Competing approaches to compare against (1)",
        "## Same problem (3)",
        "## Datasets, benchmarks, and tools (1)",
        "## Other (1)",
    ]
    assert "- **3.8** · 2011 · 10 citations · [p1](https://doi.org/10.1/1) · Sensors" in md

    write_csv(ranked, tmp_path / "ranked.csv")
    lines = (tmp_path / "ranked.csv").read_text().splitlines()
    assert lines[0].startswith("id,published,relevance")
    assert lines[1] == "p9,2019-05-01,3.6,same_problem,0.2,90,Sensors,p9,https://doi.org/10.1/9"


async def test_new_papers_are_those_from_the_latest_fetch(papers_file, tmp_path):
    results = await judge(papers_file, tmp_path)
    ranked, judged = rank(papers_file, results, RESEARCH)
    assert not any(p["is_new"] for p in ranked)  # a single fetch: nothing is "new" yet
    assert "## New since" not in render(ranked, judged, RESEARCH, 2.0)

    rows = [json.loads(line) for line in papers_file.open()]
    for row in rows:
        row["fetched_at"] = "2026-10-30" if row["id"] in {"p1", "p4"} else "2026-09-30"
    papers_file.write_text("".join(json.dumps(r) + "\n" for r in rows))
    ranked, judged = rank(papers_file, results, RESEARCH)
    assert [p["id"] for p in ranked if p["is_new"]] == ["p1"]  # p4 is new but below the cut-off
    md = render(ranked, judged, RESEARCH, 2.0)
    assert "## New since the previous fetch (1)" in md.splitlines()
