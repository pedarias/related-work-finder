from conftest import FakeBackend

from arxiv_atlas.analyze import CHOICES, NOULS, charts, checks, load, yearly
from arxiv_atlas.classify import classify
from arxiv_atlas.questions import PACK_VERSION


async def test_end_to_end_analysis(papers_file, tmp_path):
    results = tmp_path / "results.jsonl"
    await classify(papers_file, results, FakeBackend(tokens=1200), rpm=60_000, log=lambda *_: None)

    con = load(papers_file, results, PACK_VERSION)
    df = yearly(con)
    assert list(df.year) == list(range(2010, 2020)) and df.n.sum() == 20
    for q in NOULS:
        assert df[q].between(0, 1).all() and (df[f"{q}_ci"] >= 0).all()
    for q, opts in CHOICES.items():
        assert (df[[f"{q}__{o}" for o in opts]].sum(axis=1).round(6) == 1).all()

    report = checks(con)
    assert report["papers"] == 20 and report["tokens_per_paper"] == 1200
    assert report["code_url_check"]["n_with_url"] == 5
    assert report["llm_anachronism_check"]["pre_2018_n"] == 16

    paths = charts(df, tmp_path / "reports")
    assert all(p.exists() and p.stat().st_size > 0 for p in paths)


async def test_other_pack_versions_are_ignored(papers_file, tmp_path):
    results = tmp_path / "results.jsonl"
    await classify(papers_file, results, FakeBackend(), rpm=60_000, log=lambda *_: None)
    assert load(papers_file, results, "v0").execute("SELECT count(*) FROM t").fetchone()[0] == 0
