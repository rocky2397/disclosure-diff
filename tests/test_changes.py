import pytest

from disclosure_diff.changes import Status, compare_years, has_amount, similarity
from disclosure_diff.passages import Passage

BOILERPLATE = (
    "Changes in trade policy, including tariffs and sanctions, could adversely affect our "
    "operations and financial results in {year}."
)
REWORDED = (
    "Changes in trade policy, including tariffs and sanctions, adversely affected our "
    "operations: new import duties raised procurement costs by €120 million."
)
EXPORT_CONTROLS = "Export controls on turbine components delayed two projects in Asia."
DIVIDEND = "The Board proposes a dividend in line with our long-standing payout policy."


def p(year, page, text):
    return Passage("ACME", year, page, text)


def test_similarity_ignores_years_case_and_layout():
    a = BOILERPLATE.format(year=2022)
    b = BOILERPLATE.format(year=2023).upper().replace(" ", "\n", 3)
    assert similarity(a, b) == 1.0
    assert similarity(a, DIVIDEND) < 0.3
    assert similarity("", a) == 0.0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("costs rose by €120 million", True),
        ("a 25% tariff", True),
        ("USD 3.5 bn in duties", True),
        ("$40m", True),
        ("in 2023 we operated 12 plants", False),
        ("tariffs could affect us", False),
    ],
)
def test_has_amount(text, expected):
    assert has_amount(text) is expected


def test_repeated_boilerplate_is_unchanged():
    (change,) = compare_years(
        [p(2022, 40, BOILERPLATE.format(year=2022))], [p(2023, 42, BOILERPLATE.format(year=2023))]
    )
    assert change.status is Status.UNCHANGED
    assert change.before.page == 40 and change.after.page == 42


def test_rewording_that_adds_a_figure_is_changed_and_newly_quantified():
    (change,) = compare_years([p(2022, 40, BOILERPLATE.format(year=2022))], [p(2023, 42, REWORDED)])
    assert change.status is Status.CHANGED
    assert 0.4 <= change.similarity < 0.95
    assert change.newly_quantified


def test_unrelated_passages_are_new_and_dropped():
    changes = compare_years([p(2022, 40, DIVIDEND)], [p(2023, 42, EXPORT_CONTROLS)])
    assert [c.status for c in changes] == [Status.NEW, Status.DROPPED]
    assert changes[0].after.text == EXPORT_CONTROLS and changes[0].before is None
    assert changes[1].before.text == DIVIDEND and changes[1].after is None


def test_each_passage_is_paired_at_most_once():
    text = BOILERPLATE.format(year=2023)
    changes = compare_years(
        [p(2022, 40, BOILERPLATE.format(year=2022))], [p(2023, 42, text), p(2023, 90, text)]
    )
    assert sorted(c.status.value for c in changes) == ["new", "unchanged"]


def test_order_is_new_changed_dropped_unchanged():
    before = [
        p(2022, 10, BOILERPLATE.format(year=2022)),
        p(2022, 11, DIVIDEND),
        p(2022, 12, "Sanctions regimes are monitored by our compliance function every quarter."),
    ]
    after = [
        p(2023, 10, REWORDED),
        p(2023, 12, "Sanctions regimes are monitored by our compliance function every quarter."),
        p(2023, 30, EXPORT_CONTROLS),
    ]
    assert [c.status for c in compare_years(before, after)] == [
        Status.NEW,
        Status.CHANGED,
        Status.DROPPED,
        Status.UNCHANGED,
    ]


def test_empty_years():
    assert compare_years([], []) == []
    assert [c.status for c in compare_years([], [p(2023, 1, DIVIDEND)])] == [Status.NEW]


def test_paragraph_rewritten_with_new_figures_is_changed_not_new():
    # From RWE's 2024 and 2025 reports. The pair scores about 0.42.
    old = (
        "In the UK, where a national emissions trading system was established after Brexit, "
        "the cost of emitting carbon dioxide also decreased. One UK Allowance (UKA), which "
        "like one EUA, entitles the holder to emit one metric ton of carbon dioxide, averaged "
        "£41 in 2024."
    )
    new = (
        "In the United Kingdom, where a national emissions trading system was established "
        "following Brexit, CO2 costs also increased. The price of a UK Allowance (UKA) "
        "averaged £52 in 2025, compared to £41 a year earlier. Each UKA, like one EUA "
        "entitles the holder to emit one metric ton of carbon dioxide."
    )
    (change,) = compare_years([p(2024, 34, old)], [p(2025, 34, new)])
    assert change.status is Status.CHANGED
