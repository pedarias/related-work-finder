import json
import time

from conftest import FakeBackend

from arxiv_atlas.classify import RateLimiter, classify, cost_usd, estimate, read_jsonl
from arxiv_atlas.questions import PACK_VERSION


async def run(papers, out, backend, **kw):
    return await classify(papers, out, backend, rpm=60_000, concurrency=4, log=lambda *_: None, **kw)


async def test_classifies_all_and_records_usage(papers_file, tmp_path):
    out = tmp_path / "out.jsonl"
    stats = await run(papers_file, out, FakeBackend(tokens=500))
    rows = list(read_jsonl(out))
    assert stats["ok"] == 20 and stats["errors"] == 0 and stats["input_tokens"] == 10_000
    assert {r["id"] for r in rows} == {f"p{i}" for i in range(20)}
    assert all(r["pack"] == PACK_VERSION and r["model"] == "jev-1.13.0" for r in rows)


async def test_resume_skips_done_and_retries_failures(papers_file, tmp_path):
    out = tmp_path / "out.jsonl"
    first = await run(papers_file, out, FakeBackend(fail_ids={"p3", "p7"}))
    assert first["ok"] == 18 and first["errors"] == 2
    errors = [json.loads(line) for line in out.with_suffix(".errors.jsonl").open()]
    assert {e["id"] for e in errors} == {"p3", "p7"}

    backend = FakeBackend()
    second = await run(papers_file, out, backend)
    assert second["skipped_existing"] == 18 and second["ok"] == 2
    assert sorted(backend.calls) == ["p3", "p7"]
    assert len(list(read_jsonl(out))) == 20


async def test_limit(papers_file, tmp_path):
    stats = await run(papers_file, tmp_path / "out.jsonl", FakeBackend(), limit=5)
    assert stats["ok"] == 5


async def test_budget_cap_stops_early(papers_file, tmp_path):
    # 1M tokens per call costs $0.042, so a $0.10 cap allows ~3 calls (plus in-flight ones).
    stats = await run(papers_file, tmp_path / "out.jsonl", FakeBackend(tokens=1_000_000), max_cost_usd=0.10)
    assert stats["stopped_on_budget"] and 3 <= stats["ok"] < 20


async def test_rate_limiter_spaces_requests():
    limiter = RateLimiter(rpm=600)  # 0.1 s apart
    start = time.monotonic()
    for _ in range(4):
        await limiter.wait()
    assert time.monotonic() - start >= 0.29


def test_estimate_is_offline_and_scales(papers_file):
    est = estimate(papers_file, rpm=1000)
    assert est["papers"] == 20 and est["est_tokens_per_paper"] > 500
    assert est["projection_usd"][2_900_000] > est["projection_usd"][1_000_000]


def test_cost():
    assert cost_usd(1_000_000) == 0.042
