"""Yearly aggregates, sanity checks, and charts from classified results."""

from __future__ import annotations

from pathlib import Path

import duckdb

from .classify import PRICE_PER_MTOK

NOULS = ["claims_sota", "releases_artifacts", "mentions_limitations", "about_llms"]
CHOICES = {
    "contribution": [
        "new_method",
        "benchmark_or_dataset",
        "survey_or_review",
        "theory",
        "empirical_study",
        "system_or_tool",
        "position_or_perspective",
        "other",
    ],
    "evidence": ["quantitative_experiments", "formal_proof", "human_study", "qualitative_or_case_study", "none_stated"],
}
CODE_URL_RE = r"(github\.com|gitlab\.com|huggingface\.co|bitbucket\.org|zenodo\.org|sourceforge\.net)"


def load(papers: Path, results: Path, pack: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    nouls = ", ".join(f"r.answers.{q}.noul AS {q}" for q in NOULS)
    choices = ", ".join(f"r.answers.{q}.choice AS {q}, r.answers.{q}.confidence AS {q}_conf" for q in CHOICES)
    con.execute(f"""
        CREATE TABLE t AS
        SELECT p.id, year(CAST(p.published AS TIMESTAMP)) AS year, p.primary_category,
               regexp_matches(coalesce(p.abstract::VARCHAR, '') || ' ' || coalesce(p.comment::VARCHAR, ''),
                              '{CODE_URL_RE}')
                   AS has_code_url,
               {nouls}, {choices},
               r.answers.hype.score AS hype, r.usage.input_tokens AS input_tokens, r.model
        FROM read_json_auto('{papers}') p
        JOIN read_json_auto('{results}', union_by_name=true) r USING (id)
        WHERE r.pack = '{pack}'
    """)
    return con


def yearly(con: duckdb.DuckDBPyConnection):
    """Mean calibrated probability per year is the expected share of papers; CI is a normal approximation."""
    cols = ", ".join(f"avg({q}) AS {q}, 1.96 * coalesce(stddev_samp({q}), 0) / sqrt(count(*)) AS {q}_ci" for q in NOULS)
    shares = ", ".join(f"avg(({q} = '{opt}')::INT) AS {q}__{opt}" for q, opts in CHOICES.items() for opt in opts)
    return con.execute(f"""
        SELECT year, count(*) AS n, {cols}, avg(hype) AS hype,
               1.96 * coalesce(stddev_samp(hype), 0) / sqrt(count(*)) AS hype_ci, {shares}
        FROM t GROUP BY year ORDER BY year
    """).df()


def checks(con: duckdb.DuckDBPyConnection) -> dict:
    """Sanity checks against things we know without the model."""
    code = con.execute("""
        SELECT avg(releases_artifacts) FILTER (WHERE has_code_url) AS mean_p_with_url,
               avg(releases_artifacts) FILTER (WHERE NOT has_code_url) AS mean_p_without_url,
               avg((releases_artifacts >= 0.5)::INT) FILTER (WHERE has_code_url) AS recall_at_0_5,
               count(*) FILTER (WHERE has_code_url) AS n_with_url
        FROM t
    """).fetchone()
    llm = con.execute("""
        SELECT avg(about_llms) FILTER (WHERE year < 2018) AS pre_2018_mean_p,
               count(*) FILTER (WHERE year < 2018 AND about_llms >= 0.5) AS pre_2018_flagged,
               count(*) FILTER (WHERE year < 2018) AS pre_2018_n
        FROM t
    """).fetchone()
    usage = con.execute("SELECT count(*), sum(input_tokens), avg(input_tokens), any_value(model) FROM t").fetchone()
    n, tokens, per_paper, model = usage
    return {
        "papers": n,
        "model": model,
        "tokens_per_paper": round(per_paper or 0),
        "cost_usd": round((tokens or 0) * PRICE_PER_MTOK / 1e6, 4),
        "projection_usd": {
            size: round((per_paper or 0) * size * PRICE_PER_MTOK / 1e6, 2) for size in (1_000_000, 2_900_000)
        },
        "code_url_check": dict(
            zip(["mean_p_with_url", "mean_p_without_url", "recall_at_0_5", "n_with_url"], code, strict=True)
        ),
        "llm_anachronism_check": dict(zip(["pre_2018_mean_p", "pre_2018_flagged", "pre_2018_n"], llm, strict=True)),
    }


def charts(df, out_dir: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    titles = {
        "claims_sota": "Claims state of the art",
        "releases_artifacts": "Says code/data released",
        "mentions_limitations": "Mentions own limitations",
        "about_llms": "About large language models",
    }
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), sharex=True)
    for ax, q in zip(axes.flat, NOULS, strict=False):
        ax.plot(df.year, df[q] * 100, marker="o", ms=3)
        ax.fill_between(df.year, (df[q] - df[f"{q}_ci"]) * 100, (df[q] + df[f"{q}_ci"]) * 100, alpha=0.2)
        ax.set_title(titles[q])
        ax.set_ylabel("% of abstracts")
    ax = axes.flat[4]
    ax.plot(df.year, df.hype, marker="o", ms=3, color="tab:red")
    ax.fill_between(df.year, df.hype - df.hype_ci, df.hype + df.hype_ci, alpha=0.2, color="tab:red")
    ax.set_title("Hype score (0 neutral – 4 extreme)")
    ax = axes.flat[5]
    ax.bar(df.year, df.n, color="gray")
    ax.set_title("Sample size per year")
    fig.suptitle("arXiv CS abstracts over time, read by Jev (pilot)")
    fig.tight_layout()
    paths = [out_dir / "trends.png"]
    fig.savefig(paths[0], dpi=130)

    for q, opts in CHOICES.items():
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.stackplot(df.year, *[df[f"{q}__{o}"] * 100 for o in opts], labels=opts)
        ax.set_ylabel("% of abstracts")
        ax.set_title(f"{q.capitalize()} type over time")
        ax.legend(loc="upper left", bbox_to_anchor=(1, 1), fontsize=8)
        fig.tight_layout()
        paths.append(out_dir / f"{q}.png")
        fig.savefig(paths[-1], dpi=130)
    plt.close("all")
    return paths
