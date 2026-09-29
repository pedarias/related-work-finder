"""Resumable, rate-limited, budget-capped classification of papers with Jev."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from .questions import PACK_VERSION, QUESTIONS, build_state, request_json

PRICE_PER_MTOK = 0.042  # USD per million input tokens, jev-1.13.0; output is free.
DEFAULT_MODEL = "jev-1.13.0"
CHARS_PER_TOKEN = 4  # rough heuristic for pre-flight estimates only; real runs use reported usage


class Backend(Protocol):
    async def evaluate(self, state: dict) -> dict: ...


class JevBackend:
    """Official SDK client; returns the raw response as JSON-compatible dict."""

    def __init__(self, model: str = DEFAULT_MODEL):
        from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy

        self.client = AsyncTypeSafeClient(model=model, retry=RetryPolicy(max_retries=6, backoff_max=30.0))

    async def evaluate(self, state: dict) -> dict:
        response = await self.client.system_one(state, QUESTIONS)
        return response.model_dump(mode="json")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.client.aclose()


class RateLimiter:
    """Spaces request starts evenly so we stay under a requests-per-minute limit."""

    def __init__(self, rpm: float):
        self.interval = 60.0 / rpm
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + self.interval
        if delay > 0:
            await asyncio.sleep(delay)


def read_jsonl(path: Path) -> Iterator[dict]:
    if path.exists():
        with path.open() as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def cost_usd(tokens: int) -> float:
    return tokens * PRICE_PER_MTOK / 1_000_000


def estimate(papers_path: Path, rpm: float) -> dict:
    """Pre-flight estimate from request size; no API calls."""
    n, chars = 0, 0
    for paper in read_jsonl(papers_path):
        n += 1
        chars += len(request_json(paper))
    tokens_per_paper = chars / max(n, 1) / CHARS_PER_TOKEN
    return {
        "papers": n,
        "est_tokens_per_paper": round(tokens_per_paper),
        "est_cost_usd": round(cost_usd(tokens_per_paper * n), 2),
        "est_hours": round(n / rpm / 60, 2),
        "projection_usd": {size: round(cost_usd(tokens_per_paper * size), 2) for size in (1_000_000, 2_900_000)},
    }


async def classify(
    papers_path: Path,
    out_path: Path,
    backend: Backend,
    *,
    rpm: float = 1000,
    concurrency: int = 32,
    limit: int | None = None,
    max_cost_usd: float | None = None,
    log=print,
    progress_every_s: float = 15.0,
) -> dict:
    """Classify every paper not already in `out_path`. Safe to interrupt and re-run."""
    done = {row["id"] for row in read_jsonl(out_path)}
    errors_path = out_path.with_suffix(".errors.jsonl")
    todo = (p for p in read_jsonl(papers_path) if p["id"] not in done)
    if limit is not None:
        todo = (p for i, p in enumerate(todo) if i < limit)

    limiter = RateLimiter(rpm)
    stats = {"ok": 0, "errors": 0, "input_tokens": 0, "skipped_existing": len(done), "stopped_on_budget": False}
    started = last_log = time.monotonic()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("a") as out, errors_path.open("a") as err:

        def report(final: bool = False) -> None:
            elapsed = time.monotonic() - started
            rate = stats["ok"] / elapsed * 60 if elapsed else 0.0
            log(
                f"{'done' if final else 'progress'}: ok={stats['ok']} errors={stats['errors']} "
                f"rate={rate:.0f}/min tokens={stats['input_tokens']} cost=${cost_usd(stats['input_tokens']):.4f}"
            )

        async def worker() -> None:
            nonlocal last_log
            for paper in todo:
                if stats["stopped_on_budget"]:
                    return
                await limiter.wait()
                try:
                    response = await backend.evaluate(build_state(paper))
                except Exception as exc:  # recorded and retried on the next run
                    stats["errors"] += 1
                    err.write(json.dumps({"id": paper["id"], "error": f"{type(exc).__name__}: {exc}"}) + "\n")
                    err.flush()
                    continue
                tokens = (response.get("usage") or {}).get("input_tokens") or 0
                stats["ok"] += 1
                stats["input_tokens"] += tokens
                out.write(json.dumps({"id": paper["id"], "pack": PACK_VERSION, **response}) + "\n")
                out.flush()
                if max_cost_usd is not None and cost_usd(stats["input_tokens"]) >= max_cost_usd:
                    stats["stopped_on_budget"] = True
                    log(f"budget cap ${max_cost_usd} reached; stopping (re-run to continue)")
                if time.monotonic() - last_log >= progress_every_s:
                    last_log = time.monotonic()
                    report()

        await asyncio.gather(*(worker() for _ in range(concurrency)))
        report(final=True)
    stats["cost_usd"] = round(cost_usd(stats["input_tokens"]), 6)
    return stats
