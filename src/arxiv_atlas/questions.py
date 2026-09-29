"""The question pack asked of every abstract. Bump PACK_VERSION whenever any wording changes."""

from __future__ import annotations

import json

from typesafe_sdk import Choice, Noul, Score

PACK_VERSION = "v1"

QUESTIONS = {
    "claims_sota": Noul(
        instructions="Does the `abstract` claim that the paper's own method or result is state-of-the-art, "
        "or that it outperforms all existing or previous methods?",
        criteria={
            "true": "Explicitly claims state-of-the-art, best-ever, or outperforming existing or prior methods.",
            "false": "Makes no such claim, or only claims competitive, comparable, or improved-over-one-baseline "
            "results.",
        },
    ),
    "releases_artifacts": Noul(
        instructions="Does the `abstract` state that code, data, models, or other artifacts of this paper are "
        "publicly released or available?",
        criteria={
            "true": "States that code, data, or models are released, open-sourced, publicly available, or gives a "
            "link to them.",
            "false": "Does not mention making any code, data, or models available.",
        },
    ),
    "mentions_limitations": Noul(
        instructions="Does the `abstract` explicitly mention a limitation, weakness, failure case, or open problem "
        "of the paper's own work?",
        criteria={
            "true": "Names at least one limitation, weakness, failure case, or open problem of this paper's work.",
            "false": "Only describes the work and its results. Limitations of prior work do not count.",
        },
    ),
    "about_llms": Noul(
        instructions="Is the main subject of the paper large language models, such as GPT, LLaMA, or other large "
        "pretrained language models, including their training, evaluation, use, or behavior?",
        criteria={
            "true": "Large language models are the central subject of the paper.",
            "false": "Large language models are not the central subject. Classical NLP, small language models, or "
            "other neural networks do not count.",
        },
    ),
    "contribution": Choice(
        instructions="What is the main type of contribution described in the `abstract`?",
        criteria={
            "new_method": "Proposes a new method, algorithm, model, or architecture.",
            "benchmark_or_dataset": "Introduces a new benchmark, dataset, or evaluation protocol.",
            "survey_or_review": "Surveys, reviews, or summarizes existing work.",
            "theory": "Proves theorems or develops formal or mathematical theory.",
            "empirical_study": "Analyzes or measures existing methods or phenomena without proposing a new method.",
            "system_or_tool": "Describes a software system, tool, library, or implementation.",
            "position_or_perspective": "Argues a position, perspective, or research agenda.",
            "other": "None of the above.",
        },
    ),
    "evidence": Choice(
        instructions="What is the main kind of evidence the `abstract` offers for its claims?",
        criteria={
            "quantitative_experiments": "Experiments or benchmarks with measured, numeric results.",
            "formal_proof": "Mathematical proofs or formal analysis.",
            "human_study": "User studies, surveys of people, interviews, or human evaluation.",
            "qualitative_or_case_study": "Case studies, examples, demonstrations, or qualitative analysis.",
            "none_stated": "The abstract does not describe any evidence.",
        },
    ),
    "hype": Score(
        instructions="How promotional is the wording of the `abstract`?",
        criteria=[
            "Neutral, factual wording with no promotional adjectives.",
            "Mostly factual, with one or two mild positive words such as 'effective' or 'efficient'.",
            "Clearly promotional, for example 'significantly outperforms', 'novel', or 'powerful'.",
            "Strongly promotional, with several superlatives such as 'remarkable', 'unprecedented', or 'dramatically'.",
            "Extreme hype, for example 'revolutionary', 'paradigm shift', 'game-changing', or 'groundbreaking'.",
        ],
    ),
}


def build_state(paper: dict) -> dict:
    """Only the title and abstract are sent; metadata like dates and categories stays in code."""
    return {"title": paper["title"], "abstract": paper["abstract"]}


def request_json(paper: dict) -> str:
    """Serialized request body, used for rough token estimates before any paid call."""
    questions = {k: q.model_dump(mode="json", exclude_none=True) for k, q in QUESTIONS.items()}
    return json.dumps({"state": build_state(paper), "questions": questions}, ensure_ascii=False)
