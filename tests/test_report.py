from conftest import RESEARCH, FakeBackend, fake_response

from arxiv_atlas.classify import classify
from arxiv_atlas.report import rank, render, write_csv

# id -> (relevance, relation, baseline probability); papers not listed are unrelated.
JUDGEMENTS = {
    "p1": (3.8, "same_problem", 0.9),  # published 2011
    "p9": (3.6, "same_problem", 0.2),  # published 2019: same level as p1, so it comes first
    "p2": (2.4, "resource", 0.1),
    "p3": (3.1, "unrelated", 0.0),
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


async def test_rank_orders_by_level_then_newest(papers_file, tmp_path):
    ranked, judged = rank(papers_file, await judge(papers_file, tmp_path), RESEARCH)
    assert judged == 20
    assert [p["id"] for p in ranked] == ["p9", "p1", "p3", "p2"]


async def test_rank_ignores_results_for_other_research(papers_file, tmp_path):
    results = await judge(papers_file, tmp_path)
    assert rank(papers_file, results, "Something else entirely.") == ([], 0)


async def test_report_groups_and_flags_baselines(papers_file, tmp_path):
    ranked, judged = rank(papers_file, await judge(papers_file, tmp_path), RESEARCH)
    md = render(ranked, judged, RESEARCH, 2.0)
    assert md.startswith("# Related work\n\n> We predict molecular properties")
    assert "4 of 20 candidates" in md
    sections = [line for line in md.splitlines() if line.startswith("## ")]
    assert sections == [
        "## Most cited (4)",
        "## Competing approaches to compare against (1)",
        "## Same problem (2)",
        "## Datasets, benchmarks, and tools (1)",
        "## Other (1)",
    ]
    assert "- **3.8** · 2011 · 10 citations · [p1](https://doi.org/10.1/1) · Sensors" in md

    write_csv(ranked, tmp_path / "ranked.csv")
    lines = (tmp_path / "ranked.csv").read_text().splitlines()
    assert lines[0].startswith("id,published,relevance")
    assert lines[1] == "p9,2019-05-01,3.6,same_problem,0.2,90,Sensors,p9,https://doi.org/10.1/9"
