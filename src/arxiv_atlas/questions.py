"""The questions asked of every candidate paper, relative to one research description.

Bump PACK_VERSION whenever any wording changes.
"""

from __future__ import annotations

import hashlib
import json

from typesafe_sdk import Choice, Noul, Score

PACK_VERSION = "v2"

QUESTIONS = {
    "relevance": Score(
        instructions="How closely related is the paper in `title` and `abstract` to the research described in "
        "`research`, as related work that this research should know about or cite?",
        criteria=[
            "Unrelated: a different problem and different methods.",
            "Same broad field only, with no specific connection.",
            "Shares a method, task, dataset, or application with the research, but asks a different question.",
            "Closely related: a similar problem, or a very similar approach to the same kind of problem.",
            "Directly related: the same problem as the research; it must be cited.",
        ],
    ),
    "relation": Choice(
        instructions="What is the main way the paper in `title` and `abstract` relates to the research described "
        "in `research`?",
        criteria={
            "same_problem": "Addresses the same or a very similar problem, possibly with a different approach.",
            "same_method": "Uses a similar method or technique, applied to a different problem.",
            "resource": "Provides a dataset, benchmark, tool, or model that the research could use.",
            "background": "Provides background, theory, or a survey of the research's field.",
            "unrelated": "Has no meaningful connection to the research.",
        },
    ),
    "baseline": Noul(
        instructions="Does the paper in `title` and `abstract` propose a method for the same problem as the research "
        "described in `research`, so that the research should compare against it or discuss it as a competing "
        "approach?",
        criteria={
            "true": "Proposes a competing method for the same problem as the research.",
            "false": "Addresses a different problem, or proposes no method (for example a survey, dataset, or "
            "analysis).",
        },
    ),
}


def topic_key(research: str) -> str:
    """Short hash of the research description, so results for an edited description never mix."""
    return hashlib.sha256(research.strip().encode()).hexdigest()[:12]


def build_state(paper: dict, research: str) -> dict:
    """Only the research description, title, and abstract are sent; dates and categories stay in code."""
    return {"research": research.strip(), "title": paper["title"], "abstract": paper["abstract"]}


def request_json(paper: dict, research: str) -> str:
    """Serialized request body, used for rough token estimates before any paid call."""
    questions = {k: q.model_dump(mode="json", exclude_none=True) for k, q in QUESTIONS.items()}
    return json.dumps({"state": build_state(paper, research), "questions": questions}, ensure_ascii=False)
