from disclosure_diff.changes import compare_years
from disclosure_diff.judgements import Concreteness, Direction, Judgement, Relevance
from disclosure_diff.passages import Passage
from disclosure_diff.report import describe, quote, render_changes
from disclosure_diff.topics import PROTECTIONISM

OLD = "Changes in trade policy, including tariffs and sanctions, could adversely affect us."
REWORDED = (
    "Changes in trade policy, including tariffs and sanctions, adversely affected us: "
    "import duties raised costs by €120 million."
)


def p(year, page, text):
    return Passage("ACME", year, page, text)


def test_quote_cites_the_page_and_cuts_at_a_word():
    text = quote(p(2023, 42, "alpha beta\ngamma delta"), max_chars=16)
    assert text == "> alpha beta gamma […]\n>\n> ACME Annual Report 2023, p. 42"
    assert quote(p(2023, 42, "alpha beta gamma delta"), max_chars=14).startswith("> alpha beta […]")
    assert quote(p(2023, 42, "short"), max_chars=14).startswith("> short\n")


def test_report_sections_and_citations():
    before = [p(2022, 40, OLD), p(2022, 41, "Our embargo screening process was extended.")]
    after = [p(2023, 42, REWORDED), p(2023, 60, "Export controls delayed two projects.")]
    text = render_changes("ACME", PROTECTIONISM, 2022, 2023, compare_years(before, after))

    assert text.startswith("# ACME: Protectionism, 2022 to 2023\n")
    assert "1 new, 1 changed, 1 dropped, 0 unchanged." in text
    assert "1 new or changed passages state an amount that was not there before." in text
    sections = [line for line in text.splitlines() if line.startswith("## ")]
    assert sections == ["## New in 2023", "## Changed from 2022 to 2023", "## Dropped after 2022"]
    assert "> Export controls delayed two projects.\n>\n> ACME Annual Report 2023, p. 60" in text
    assert "States an amount that the 2022 text did not." in text
    assert "ACME Annual Report 2022, p. 41" in text


def test_unchanged_passages_are_listed_only_on_request():
    changes = compare_years([p(2022, 40, OLD)], [p(2023, 42, OLD)])
    assert "## Unchanged" not in render_changes("ACME", PROTECTIONISM, 2022, 2023, changes)
    assert "## Unchanged" in render_changes(
        "ACME", PROTECTIONISM, 2022, 2023, changes, include_unchanged=True
    )


def test_empty_report_says_so():
    text = render_changes("ACME", PROTECTIONISM, 2022, 2023, [])
    assert "No passages about protectionism were found in either report." in text


def judgement(passage, concreteness, *, response=False, relevance=Relevance.COMPANY):
    return Judgement(
        passage_id=passage.id,
        relevance=relevance,
        direction=Direction.RISK,
        concreteness=concreteness,
        states_response=response,
        evidence="",
        evidence_verified=False,
        model="claude-opus-5-5",
    )


def test_describe():
    passage = p(2023, 1, OLD)
    assert describe(judgement(passage, Concreteness.GENERIC)) == "Risk, generic."
    assert (
        describe(judgement(passage, Concreteness.QUANTIFIED, response=True))
        == "Risk, quantified, says what the company does about it."
    )
    context = judgement(passage, Concreteness.GENERIC, relevance=Relevance.CONTEXT)
    assert describe(context) == "Background, not about the company."


def test_report_with_judgements_shows_them_instead_of_the_amount_flag():
    old, new = p(2022, 40, OLD), p(2023, 42, REWORDED)
    added = p(2023, 60, "Export controls delayed two projects, costing €5 million.")
    judgements = {
        old.id: judgement(old, Concreteness.GENERIC),
        new.id: judgement(new, Concreteness.QUANTIFIED),
        added.id: judgement(added, Concreteness.SPECIFIC, response=True),
    }
    text = render_changes(
        "ACME",
        PROTECTIONISM,
        2022,
        2023,
        compare_years([old], [new, added]),
        judgements=judgements,
        notes=["Judged by claude-opus-5-5."],
    )

    assert "1 new, 1 changed, 0 dropped, 0 unchanged.\n\nJudged by claude-opus-5-5.\n" in text
    assert "state an amount" not in text and "States an amount" not in text
    assert "p. 60\n\nRisk, specific, says what the company does about it.\n" in text
    assert "Risk, quantified. Similarity " in text
    assert text.rstrip().endswith("In 2022 this was generic.")


def test_key_sentence_is_shown_when_the_quote_was_cut_before_it():
    filler = "Our investment decisions follow a fixed approval process. " * 3
    text = filler + "New import duties raised procurement costs by €120 million."
    passage = p(2023, 42, text)
    evidence = "New import duties raised procurement costs by €120 million."
    verdict = judgement(passage, Concreteness.QUANTIFIED)
    verdict = Judgement(**{**verdict.__dict__, "evidence": evidence, "evidence_verified": True})
    changes = compare_years([], [passage])

    def render(max_chars):
        return render_changes(
            "ACME",
            PROTECTIONISM,
            2022,
            2023,
            changes,
            judgements={passage.id: verdict},
            max_chars=max_chars,
        )

    assert f"Risk, quantified. Key sentence, after the cut: “{evidence}”" in render(80)
    assert "Key sentence" not in render(700)


def test_evidence_from_a_neighbouring_paragraph_is_quoted_under_the_passage():
    passage = p(2023, 31, "In April the US government announced new tariffs on most imports.")
    evidence = "The measures raise the cost of components for our US projects."
    verdict = judgement(passage, Concreteness.SPECIFIC)
    verdict = Judgement(
        **{
            **verdict.__dict__,
            "evidence": evidence,
            "evidence_verified": True,
            "evidence_from": "after",
            "saw_neighbours": True,
        }
    )
    text = render_changes(
        "ACME",
        PROTECTIONISM,
        2022,
        2023,
        compare_years([], [passage]),
        judgements={passage.id: verdict},
    )
    assert (
        "Risk, specific. The link to the company is stated in the paragraph after it: "
        f"“{evidence}”" in text
    )
