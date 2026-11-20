import pytest

from disclosure_diff.changes import Status, compare_years, unmatched
from disclosure_diff.pairing import (
    Pair,
    Pairing,
    build_pair_request,
    pairing_path,
    pairs_from_answer,
    read_pairing,
    write_pairing,
)
from disclosure_diff.passages import Passage
from disclosure_diff.settings import DataDir
from disclosure_diff.topics import PROTECTIONISM

# The same statement in other words: wording alone does not match these two.
OLD_RISK = Passage(
    "ACME",
    2024,
    64,
    "Should further import duties be imposed on solar modules, our projects in North America "
    "would become more expensive to build.",
    section="2.9 Risks",
)
NEW_RISK = Passage(
    "ACME",
    2025,
    66,
    "Tariffs announced in April raise procurement costs for US photovoltaic plants by an "
    "estimated €40 million.",
    section="2.9 Risks",
)
OLD_OTHER = Passage("ACME", 2024, 70, "Our embargo screening was extended to all suppliers.")
NEW_OTHER = Passage("ACME", 2025, 12, "Export controls delayed the delivery of two turbines.")
EARLIER, LATER = [OLD_RISK, OLD_OTHER], [NEW_OTHER, NEW_RISK]


def test_request_numbers_the_passages_of_both_years():
    text = build_pair_request(EARLIER, LATER, PROTECTIONISM)
    assert text.startswith(
        "Topic: Protectionism\nCompany: ACME\nEarlier report: 2024. Later report: 2025."
    )
    assert '<earlier>\nE1 (section "2.9 Risks", page 64)\nShould further import duties' in text
    assert "\n\nE2 (page 70)\nOur embargo screening" in text
    assert "<later>\nL1 (page 12)\nExport controls" in text
    assert text.endswith("€40 million.\n</later>")


def test_numbers_become_pairs_of_passage_ids():
    answer = {"pairs": [{"earlier": 1, "later": 2}]}
    assert pairs_from_answer(answer, EARLIER, LATER, "test-model") == [
        Pair(OLD_RISK.id, NEW_RISK.id, "test-model")
    ]
    assert pairs_from_answer({"pairs": []}, EARLIER, LATER, "test-model") == []


def test_a_passage_is_paired_once_and_unknown_numbers_are_refused():
    twice = {"pairs": [{"earlier": 1, "later": 2}, {"earlier": 2, "later": 2}]}
    assert len(pairs_from_answer(twice, EARLIER, LATER, "test-model")) == 1
    with pytest.raises(ValueError, match="E3 and L1 do not both name a passage"):
        pairs_from_answer({"pairs": [{"earlier": 3, "later": 1}]}, EARLIER, LATER, "test-model")


def test_pairing_round_trip(tmp_path):
    path = pairing_path(DataDir(tmp_path), "ACME", 2024, 2025, "protectionism")
    assert path.name == "ACME_2024_2025_protectionism.json"
    assert read_pairing(path) is None

    pairing = Pairing(
        [Pair(OLD_RISK.id, NEW_RISK.id, "test-model")],
        frozenset(p.id for p in EARLIER + LATER),
    )
    write_pairing(path, pairing)
    assert read_pairing(path) == pairing


def test_wording_alone_reports_a_rewritten_passage_as_dropped_and_new():
    changes = compare_years(EARLIER, LATER)
    assert sorted(change.status.value for change in changes) == ["dropped"] * 2 + ["new"] * 2
    assert unmatched(changes) == ([OLD_RISK, OLD_OTHER], [NEW_OTHER, NEW_RISK])


def test_a_pair_turns_a_dropped_and_a_new_passage_into_a_changed_one():
    pair = Pair(OLD_RISK.id, NEW_RISK.id, "test-model")
    changes = compare_years(EARLIER, LATER, pairs=[pair])

    assert [change.status for change in changes] == [Status.NEW, Status.CHANGED, Status.DROPPED]
    changed = changes[1]
    assert (changed.before, changed.after, changed.paired_by) == (OLD_RISK, NEW_RISK, "test-model")
    assert changed.similarity < 0.4 and changed.newly_quantified


def test_a_pair_does_not_undo_a_match_by_wording():
    same = Passage("ACME", 2025, 65, OLD_RISK.text, section="2.9 Risks")
    pair = Pair(OLD_RISK.id, NEW_RISK.id, "test-model")
    changes = compare_years([OLD_RISK], [same, NEW_RISK], pairs=[pair])
    assert [(c.status, c.paired_by) for c in changes] == [
        (Status.NEW, None),
        (Status.UNCHANGED, None),
    ]
    # A pair that names a passage which is not being compared is ignored.
    stale = Pair("no-such-id", NEW_RISK.id, "test-model")
    assert [c.status for c in compare_years([OLD_RISK], [NEW_RISK], pairs=[stale])] == [
        Status.NEW,
        Status.DROPPED,
    ]


def test_passages_of_a_filing_are_listed_without_a_page():
    earlier = [Passage("CVX", 2024, 0, "Tariffs may be imposed.", "Item 1A. Risk Factors")]
    later = [Passage("CVX", 2025, 0, "Tariffs were imposed.")]
    text = build_pair_request(earlier, later, PROTECTIONISM)
    assert 'E1 (section "Item 1A. Risk Factors")\nTariffs may be imposed.' in text
    assert "L1\nTariffs were imposed." in text
