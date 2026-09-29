import random

import pytest

from arxiv_atlas.fetch import month_query, months, parse_feed, sample_month

FEED = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns:arxiv="http://arxiv.org/schemas/atom"
      xmlns="http://www.w3.org/2005/Atom">
  <opensearch:totalResults>48</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/cs/0301008v2</id>
    <title>Formal Concept
      Analysis</title>
    <summary>  We relate two
      areas. </summary>
    <category term="cs.LO" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
    <published>2003-01-09T23:37:57Z</published>
    <arxiv:comment>14 pages</arxiv:comment>
    <arxiv:primary_category term="cs.LO"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2301.00001v1</id>
    <title>New style id</title>
    <summary>Abstract.</summary>
    <published>2023-01-01T00:00:00Z</published>
  </entry>
</feed>"""

ERROR_FEED = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry><id>https://arxiv.org/api/errors</id><summary>max_results must be positive</summary></entry>
</feed>"""


def test_parse_feed_normalizes_entries():
    total, papers = parse_feed(FEED)
    assert total == 48
    old, new = papers
    assert old["id"] == "cs/0301008" and old["version"] == "v2"
    assert old["title"] == "Formal Concept Analysis"
    assert old["abstract"] == "We relate two areas."
    assert old["categories"] == ["cs.LO", "cs.AI"] and old["primary_category"] == "cs.LO"
    assert old["comment"] == "14 pages"
    assert new["id"] == "2301.00001" and new["comment"] is None and new["primary_category"] is None


def test_parse_feed_raises_on_api_error():
    with pytest.raises(RuntimeError, match="max_results"):
        parse_feed(ERROR_FEED)


def test_months_crosses_year_boundary():
    assert list(months("202311", "202402")) == ["202311", "202312", "202401", "202402"]


@pytest.mark.parametrize("month,last", [("202302", "28"), ("202402", "29"), ("202304", "30"), ("202312", "31")])
def test_month_query_uses_real_last_day(month, last):
    assert month_query("cs.*", month).endswith(f"TO {month}{last}2359]")


class FakeAPI:
    def __init__(self, total):
        self.total, self.calls = total, []

    def query(self, q, start, max_results):
        self.calls.append((start, max_results))
        n = max(0, min(max_results, self.total - start))
        return self.total, [{"id": f"p{start + i}"} for i in range(n)]


def test_sample_month_retries_when_hint_overshoots():
    api = FakeAPI(total=40)
    total, papers = sample_month(api, "cs.*", "202301", 10, random.Random(1), total_hint=10_000)
    assert total == 40 and len(papers) == 10
    assert all(p["sample_month"] == "202301" and p["month_total"] == 40 for p in papers)


def test_sample_month_counts_first_without_hint():
    api = FakeAPI(total=25)
    total, papers = sample_month(api, "cs.*", "202301", 10, random.Random(1), total_hint=None)
    assert api.calls[0] == (0, 1) and len(papers) == 10 and total == 25
