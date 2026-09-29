# AGENTS.md

## Commands
- Install: `uv sync`
- Verify (run before finishing any change): `uv run pytest && uv run ruff check . && uv run ruff format --check .`
- Pipeline: `uv run arxiv-atlas {fetch,estimate,classify,analyze} --help`

## Rules
- Never read, print, or write `TYPESAFE_API_KEY`; the user sets it in their own shell.
- `classify` spends real money: always pass `--max-cost`, and run `estimate` first.
- Changing any question wording in `src/arxiv_atlas/questions.py` requires bumping `PACK_VERSION`.
- Pin models to versioned IDs (`jev-1.13.0`), not `jev-latest`.
- SDK pinned to `typesafe-sdk==0.7.1` (0.7.2 was < 7 days old when added).
- arXiv API: keep >= 3 s between requests (`REQUEST_DELAY_S`); feb/short months need the real last day in date queries.
- `data/` is gitignored (large, regenerable); tests use fakes and never call external APIs.
