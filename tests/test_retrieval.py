import pytest

from disclosure_diff.passages import Passage
from disclosure_diff.retrieval import find_candidates, find_matches
from disclosure_diff.topics import (
    ARTIFICIAL_INTELLIGENCE,
    COVID,
    CYBERSECURITY,
    PROTECTIONISM,
)


def phrases(text):
    return [match.phrase for match in find_matches(text, PROTECTIONISM)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("New Tariffs were announced.", ["tariff"]),
        ("Anti-dumping measures", ["anti-dumping"]),
        ("antidumping and anti dumping duties", ["anti-dumping", "anti-dumping"]),
        ("anti-\ndumping proceedings", ["anti-dumping"]),
        ("higher customs duties", ["customs duty"]),
        ("trade-barriers and trade   wars", ["trade barrier", "trade war"]),
        ("entities sanctioned by the EU", ["sanction"]),
        ("two embargoes", ["embargo"]),
    ],
)
def test_phrase_forms(text, expected):
    assert phrases(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Trade receivables and trade marks of the group",
        "the quotation of our shares",
        "a non-tariffication clause",  # not a whole-word match
        "foreign currency effects",
    ],
)
def test_unrelated_text_does_not_match(text):
    assert phrases(text) == []


def test_utility_price_plans_are_excluded():
    assert phrases("Feed-in tariffs and network tariffs fell.") == []
    # From RWE's 2024 report, about a Dutch grid charge.
    assert phrases("The possible introduction of a general tariff on electricity feed-ins") == []
    assert phrases("Feed-in tariffs fell while import tariffs on modules rose.") == ["tariff"]


def test_offsets_refer_to_normalized_text():
    (match,) = find_matches("Costs  rose due to\nnew tariffs.", PROTECTIONISM)
    assert "Costs rose due to new tariffs."[match.start : match.end] == "tariffs"


def test_candidates_report_distinct_phrases_and_skip_tables():
    prose = Passage("BP", 2023, 40, "Sanctions and tariffs, and further sanctions, hit us.")
    table = Passage("BP", 2023, 220, "Tariff income 22,307 17 12,926 19 2,874 472 2,628 637")
    other = Passage("BP", 2023, 41, "Our dividend policy is unchanged.")

    (candidate,) = find_candidates([prose, table, other], PROTECTIONISM)
    assert candidate.passage is prose
    assert candidate.phrases == ("sanction", "tariff")
    assert len(candidate.matches) == 3

    assert len(find_candidates([prose, table, other], PROTECTIONISM, skip_tables=False)) == 2


def test_none_of_the_old_false_positives_is_a_candidate(old_false_positives):
    passages = [Passage("X", 2023, i, text) for i, text in enumerate(old_false_positives)]
    assert find_candidates(passages, PROTECTIONISM, skip_tables=False) == []


def test_a_trade_restriction_said_in_other_words_is_found():
    # The one passage a scan of RWE's 2025 report showed the search had missed.
    text = "If cross-border trade is limited, it may prove impossible to deliver certain projects."
    assert [match.phrase for match in find_matches(text, PROTECTIONISM)] == ["cross-border trade"]


@pytest.mark.parametrize(
    ("topic", "text", "found"),
    [
        (ARTIFICIAL_INTELLIGENCE, "Demand from AI and new data centres is rising.", 2),
        (ARTIFICIAL_INTELLIGENCE, "We use AI-based forecasting for our wind farms.", 1),
        # Not the letters inside another word.
        (ARTIFICIAL_INTELLIGENCE, "We maintain and repair our plants; this is fair.", 0),
        (COVID, "Restrictions during the COVID-19 pandemic delayed construction.", 2),
        (COVID, "The corona crisis and repeated lockdowns reduced demand.", 2),
        (CYBERSECURITY, "There is a significant risk of cyber attacks on our systems.", 1),
        (CYBERSECURITY, "Cyber-security training and IT security audits are mandatory.", 2),
        (CYBERSECURITY, "Security of supply remains our priority.", 0),
    ],
)
def test_the_newer_topics_find_their_phrases(topic, text, found):
    assert len(find_matches(text, topic)) == found


def test_ai_misread_by_ocr_is_still_found():
    # Chevron's 2025 report, read by OCR: the capital I came out as a lowercase l.
    text = "We're also leveraging Al to create value. Aluminium and Al-Khafji are not meant."
    assert find_matches(text, ARTIFICIAL_INTELLIGENCE) == ()
    (match,) = find_matches(text, ARTIFICIAL_INTELLIGENCE, ocr=True)
    assert (match.phrase, text[match.start : match.end]) == ("ai", "Al")

    read_by_ocr = Passage("CHEVRON", 2025, 11, text, ocr=True)
    typed = Passage("CHEVRON", 2025, 11, text)
    assert [c.passage for c in find_candidates([read_by_ocr, typed], ARTIFICIAL_INTELLIGENCE)] == [
        read_by_ocr
    ]


def test_a_compound_with_ai_set_with_a_lowercase_l_is_found_in_any_text():
    # RWE's 2025 report has this in its own text, not through OCR.
    text = "We monitor fish with cameras, along with Al-powered video analyses."
    (match,) = find_matches(text, ARTIFICIAL_INTELLIGENCE)
    assert text[match.start : match.end] == "Al"
    # A name keeps its capital after the hyphen and is not taken for AI, with or without OCR.
    assert find_matches("Production in Al-Khafji resumed.", ARTIFICIAL_INTELLIGENCE) == ()
    assert find_matches("Production in Al-Khafji resumed.", ARTIFICIAL_INTELLIGENCE, ocr=True) == ()


def test_a_paragraph_a_filing_repeats_in_another_item_is_found_once():
    text = "Export controls have harmed our competitive position in several markets."
    first = Passage("ACME", 2025, 0, text, section="Item 1. Business", form="10-K")
    again = Passage("ACME", 2025, 0, text, section="Item 1A. Risk Factors", form="10-K")
    other = Passage("ACME", 2025, 0, "New tariffs raised our costs.", section="Item 7", form="10-K")
    assert first.id == again.id
    found = [c.passage for c in find_candidates([first, again, other], PROTECTIONISM)]
    assert found == [first, other]
    # The same words on another page of a printed report are another passage.
    pages = [Passage("ACME", 2025, 12, text), Passage("ACME", 2025, 80, text)]
    assert len(find_candidates(pages, PROTECTIONISM)) == 2
