# arxiv-atlas

Decades of arXiv abstracts, read by a decision model.

Every abstract gets the same seven typed questions, answered by TypeSafe's
[Jev](https://docs.typesafe.ai) (`jev-1.13.0`) with calibrated probabilities:

| Question | Type | What it measures |
| --- | --- | --- |
| `claims_sota` | noul | Claims state-of-the-art / beating all prior methods |
| `releases_artifacts` | noul | Says code, data, or models are released |
| `mentions_limitations` | noul | Names a limitation of its own work |
| `about_llms` | noul | Large language models are the central subject |
| `contribution` | choice | New method, benchmark, survey, theory, empirical study, system, position, other |
| `evidence` | choice | Experiments, proofs, human study, case study, none stated |
| `hype` | score | Promotional wording, 0 (neutral) to 4 (extreme) |

Wording lives in `src/arxiv_atlas/questions.py`; any change bumps `PACK_VERSION` so results never mix.

> Status: pilot. Numbers describe **abstracts**, not full papers.

## Quick start

```sh
uv sync
uv run arxiv-atlas fetch                        # ~10k CS abstracts, 30 per month since 1998 (arXiv API, resumable)
uv run arxiv-atlas estimate                     # offline token / cost / time estimate
export TYPESAFE_API_KEY=...                     # set in your own shell; never commit it
uv run arxiv-atlas classify --max-cost 1        # resumable; stops at the budget cap
uv run arxiv-atlas analyze                      # reports/yearly.csv, checks.json, charts
```

## Method notes

- **Sampling (pilot):** a random contiguous slice of papers per month from the arXiv API, so every year has
  a similar sample size. Yearly figures are per-year rates, not volume-weighted totals.
- **Rates:** the yearly value is the mean of Jev's calibrated probabilities (the expected share of abstracts),
  with a 95% normal-approximation interval.
- **Built-in sanity checks:** abstracts/comments with a GitHub/GitLab/Hugging Face/Zenodo link should score high
  on `releases_artifacts`; papers before 2018 should almost never be `about_llms`.
- **Only title and abstract are sent** to the model. Dates, categories, and all arithmetic stay in code.

## Development

```sh
uv run pytest && uv run ruff check . && uv run ruff format --check .
```
