from document_impact_analyzer.passages import (
    Neighbours,
    Passage,
    find_neighbours,
    normalize,
    read_jsonl,
    write_jsonl,
)


def test_normalize_joins_hyphenated_line_breaks():
    assert (
        normalize("anti-\ndumping  duties\nwere im-\n posed") == "antidumping duties were imposed"
    )


def test_id_ignores_layout_but_not_content():
    a = Passage("BP", 2023, 12, "Tariffs  rose\nsharply.")
    b = Passage("BP", 2023, 12, "Tariffs rose sharply.")
    c = Passage("BP", 2023, 13, "Tariffs rose sharply.")
    assert a.id == b.id
    assert a.id != c.id
    assert len(a.id) == 12


def test_citation_names_report_and_page():
    assert Passage("RWE", 2022, 169, "x").citation == "RWE Annual Report 2022, p. 169"


def test_citation_says_when_the_text_was_read_by_ocr():
    scanned = Passage("RWE", 1998, 12, "x", ocr=True)
    assert scanned.citation == "RWE Annual Report 1998, p. 12, read by OCR"
    # The same words give the same id, however they were read.
    assert scanned.id == Passage("RWE", 1998, 12, "x").id


def test_passages_written_before_the_ocr_marker_still_load(tmp_path):
    path = tmp_path / "old.jsonl"
    path.write_text(
        '{"company": "RWE", "year": 2024, "page": 7, "text": "x", "section": null}\n',
        encoding="utf-8",
    )
    assert list(read_jsonl(path)) == [Passage("RWE", 2024, 7, "x")]


def test_jsonl_round_trip(tmp_path):
    passages = [
        Passage("E.ON", 2021, 5, "Größere Risiken – „Zölle“", section="Risk report"),
        Passage("BP", 2023, 7, "No section"),
    ]
    path = tmp_path / "passages.jsonl"
    assert write_jsonl(passages, path) == 2
    assert list(read_jsonl(path)) == passages


def test_neighbours_are_the_paragraphs_printed_before_and_after():
    report = [
        Passage("RWE", 2025, 30, "End of the previous chapter.", section="1.3 Strategy"),
        Passage("RWE", 2025, 31, "New tariffs were announced.", section="2.1 Environment"),
        Passage("RWE", 2025, 32, "They concern parts we buy.", section="2.1 Environment"),
        Passage("RWE", 2025, 34, "Two pages on, another matter.", section="2.1 Environment"),
    ]
    found = find_neighbours(report)

    # Another section is not a neighbour, and neither is a paragraph two pages away.
    assert found[report[1].id] == Neighbours(None, report[2])
    assert found[report[2].id] == Neighbours(report[1], None)
    assert not found[report[3].id] and not found[report[0].id]
    assert found[report[1].id]


def test_a_filing_without_pages_is_cited_by_its_section():
    passage = Passage(
        "CVX", 2024, 0, "Tariffs could raise our costs.", "Item 1A. Risk Factors", form="10-K"
    )
    assert passage.document == "Form 10-K 2024"
    assert passage.where == "Item 1A. Risk Factors"
    assert passage.citation == "CVX Form 10-K 2024, Item 1A. Risk Factors"
    # A report with pages is cited as before.
    assert Passage("RWE", 2022, 169, "x", "2.9 Risks").where == "p. 169"
    assert Passage("CVX", 2024, 0, "x").where == "no section"
