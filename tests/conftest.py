import json

import pytest

from arxiv_atlas.questions import QUESTIONS

RESEARCH = "We predict molecular properties with graph neural networks."


def fake_response(paper_id: str, tokens: int = 1000) -> dict:
    """A response shaped like SystemOneResponse.model_dump(mode='json'), deterministic per paper."""
    h = (sum(map(ord, paper_id)) % 100) / 100
    answers = {}
    for key, q in QUESTIONS.items():
        if q.type == "noul":
            answers[key] = {"type": "noul", "noul": h}
        elif q.type == "choice":
            options = list(q.criteria)
            pick = options[int(h * len(options))]
            answers[key] = {
                "type": "choice",
                "choice": pick,
                "confidence": 0.8,
                "probabilities": {o: (1.0 if o == pick else 0.0) for o in options},
            }
        else:
            answers[key] = {
                "type": "score",
                "score": h * (len(q.criteria) - 1),
                "confidence": 0.7,
                "legend": {str(i): c for i, c in enumerate(q.criteria)},
                "probabilities": {str(i): 1 / len(q.criteria) for i in range(len(q.criteria))},
            }
    return {"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": tokens, "output_tokens": 20}}


class FakeBackend:
    def __init__(self, fail_ids=(), tokens=1000):
        self.fail_ids, self.tokens, self.calls = set(fail_ids), tokens, []

    async def evaluate(self, state: dict) -> dict:
        self.calls.append(state["title"])
        if state["title"] in self.fail_ids:
            raise RuntimeError("boom")
        return fake_response(state["title"], self.tokens)


@pytest.fixture
def papers_file(tmp_path):
    path = tmp_path / "papers.jsonl"
    with path.open("w") as f:
        for i in range(20):
            year = 2010 + i % 10
            f.write(
                json.dumps(
                    {
                        "id": f"p{i}",
                        "title": f"p{i}",
                        "abstract": f"Abstract {i}.",
                        "published": f"{year}-05-01T00:00:00Z",
                        "venue": "Sensors",
                        "cited_by_count": i * 10,
                        "url": f"https://doi.org/10.1/{i}",
                        "found_by": "description (semantic)",
                    }
                )
                + "\n"
            )
    return path
