from scripts.evaluate import hit_rate, mrr, rank_of, verification_rate

# A hand-computed example: hit@3 = 16/20, MRR@3 = 13.83/20, verification rate = 33/41.
RANKS = [1] * 12 + [2] * 3 + [3] + [None] * 4
STATUSES = ["verified"] * 33 + ["unverified"] * 7 + ["approximate"]


def test_the_rank_counts_from_1():
    assert rank_of([5, 2, 9], 5) == 1
    assert rank_of([5, 2, 9], 9) == 3


def test_a_labeled_page_that_was_not_retrieved_has_no_rank():
    assert rank_of([5, 2, 9], 4) is None


def test_the_metrics_match_the_worked_example():
    assert round(hit_rate(RANKS), 2) == 0.80
    assert round(mrr(RANKS), 2) == 0.69
    assert round(verification_rate(STATUSES), 2) == 0.80


def test_only_verified_counts_as_verified():
    assert verification_rate(["approximate", "unverified"]) == 0


def test_answers_with_no_citations_verify_nothing():
    assert verification_rate([]) == 0
