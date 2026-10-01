# arxiv-atlas

Find the related work for your research, judged by a decision model.

Describe your research in a few sentences. arxiv-atlas collects candidates from
[OpenAlex](https://openalex.org) (journals, conferences, and preprints, with citation counts), then TypeSafe's
[Jev](https://docs.typesafe.ai) (`jev-1.13.0`) reads every candidate abstract next to your description and
answers three typed questions:

| Question | Type | What it tells you |
| --- | --- | --- |
| `relevance` | score | 0 unrelated, 1 same field, 2 shares a method/task/dataset, 3 closely related, 4 same problem |
| `relation` | choice | Same problem, same method on another problem, usable resource, background, unrelated |
| `baseline` | noul | A competing method you should compare against or discuss |

The output is `report.md`: most related first, **newest first within each level**, grouped by relation, plus
the most cited papers and a list of competing approaches. Wording lives in `src/arxiv_atlas/questions.py`; any
change bumps `PACK_VERSION`, and editing your description re-judges everything, so results never mix.

> Status: early. Judgements read **abstracts** only; papers without an abstract in OpenAlex are skipped.

## Quick start

```sh
uv sync
mkdir -p data/thesis
$EDITOR data/thesis/research.txt                      # 3–5 sentences: problem, method, data
uv run arxiv-atlas fetch thesis --query "road weather classification" --query "BDD100K"
uv run arxiv-atlas estimate thesis                    # offline token / cost estimate
export TYPESAFE_API_KEY=...                           # set in your own shell; never commit it
uv run arxiv-atlas classify thesis --max-cost 0.5     # resumable; stops at the budget cap
uv run arxiv-atlas report thesis                      # data/thesis/report.md and ranked.csv
```

Re-running `fetch` with new queries only adds unseen papers.

## Method notes

- **Searches:** a semantic search on your description (OpenAlex embeddings of titles and abstracts, top 50),
  and for each `--query` a semantic search plus two keyword searches over titles and abstracts: newest first
  (so recent work is never crowded out) and by relevance (so older work still shows up), `--per-query` each.
- **Duplicates:** the same paper indexed twice (preprint and journal version) is dropped by normalized title.
- **Cost:** OpenAlex is free up to $0.10/day without a key ($0.001 per request; a fetch with 6 queries uses 19).
  Judging ~1,200 candidates with Jev costs about $0.06.
- **Ranking:** papers are grouped by rounded relevance level, newest first within a level. Use
  `--min-relevance` to widen or narrow the list.
- **Only your description, the title, and the abstract are sent** to the model. Dates and citations stay in code.

## Development

```sh
uv run pytest && uv run ruff check . && uv run ruff format --check .
```
