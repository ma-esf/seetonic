from scripts.evaluate import hit_rate, mrr, verification_rate

# A hand-computed example: hit@3 = 16/20, MRR@3 = 13.83/20, verification rate = 33/41.
RANKS = [1] * 12 + [2] * 3 + [3] + [None] * 4
STATUSES = ["verified"] * 33 + ["unverified"] * 7 + ["approximate"]


def test_the_metrics_match_the_worked_example():
    assert round(hit_rate(RANKS), 2) == 0.80
    assert round(mrr(RANKS), 2) == 0.69
    assert round(verification_rate(STATUSES), 2) == 0.80
