from scripts.evaluate import answer_accuracy, answer_holds, hit_rate, mrr, verification_rate

# A hand-computed example: hit@3 = 16/20, MRR@3 = 13.83/20, verification rate = 33/41, answer accuracy = 15/20.
RANKS = [1] * 12 + [2] * 3 + [3] + [None] * 4
STATUSES = ["verified"] * 33 + ["unverified"] * 7 + ["approximate"]
CORRECT = [True] * 15 + [False] * 5

BONDS = [["49,091"]]


def test_the_metrics_match_the_worked_example():
    assert round(hit_rate(RANKS), 2) == 0.80
    assert round(mrr(RANKS), 2) == 0.69
    assert round(verification_rate(STATUSES), 2) == 0.80
    assert answer_accuracy(CORRECT) == 0.75


def test_a_fact_holds_in_plain_and_bold_text():
    assert answer_holds("Apple held $49,091 million in corporate bonds.", BONDS)
    assert answer_holds("$**49,091** million", BONDS)


def test_a_fact_fails_for_another_number_or_a_longer_one():
    assert not answer_holds("$46,560 million", BONDS)
    assert not answer_holds("$149,091 million", BONDS)
    assert not answer_holds("49,091.5", BONDS)


def test_every_fact_must_hold():
    assert not answer_holds("$26.7 billion, recognized over time", [["26.7 billion"], ["2.7 years"]])


def test_case_does_not_matter_and_any_spelling_counts():
    assert answer_holds("A rate below 21 Percent", [["21%", "21 percent"]])


def test_a_spelling_broken_across_a_line_break_holds():
    assert answer_holds("Apple was fined under the Digital\nMarkets Act.", [["Digital Markets Act"]])
