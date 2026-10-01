# AGENTS.md

## Commands
- Install: `uv sync`
- Verify (run before finishing any change): `uv run pytest && uv run ruff check . && uv run ruff format --check .`
- Pipeline: `uv run arxiv-atlas {fetch,estimate,classify,report} <topic> --help` (files live in `data/<topic>/`)

## Rules
- Never read, print, or write `TYPESAFE_API_KEY`; the user sets it in their own shell.
- `classify` spends real money: always pass `--max-cost`, and run `estimate` first.
- Changing any question wording in `src/arxiv_atlas/questions.py` requires bumping `PACK_VERSION`.
- Pin models to versioned IDs (`jev-1.13.0`), not `jev-latest`.
- SDK pinned to `typesafe-sdk==0.7.1` (0.7.2 was < 7 days old when added).
- OpenAlex API: keep >= 1.1 s between requests (`REQUEST_DELAY_S`; semantic search allows 1/s). Without a key the
  free budget is $0.10/day at $0.001 per request; check `x-ratelimit-remaining-usd` before large fetches.
- `data/` is gitignored (it holds the user's research descriptions); tests use fakes and never call external APIs.
