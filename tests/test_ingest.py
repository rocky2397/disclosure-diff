from document_impact_analyzer.ingest import (
    body_font_size,
    extract_passages,
    extraction_allowed,
    read_blocks,
    read_sections,
)
from document_impact_analyzer.sections import Section


def test_sections_come_from_the_bookmarks(report_pdf):
    assert read_sections(report_pdf) == [
        Section("1 To our investors", 1),
        Section("2 Combined management report", 2),
        Section("2.1 Risks and opportunities", 2, ("2 Combined management report",)),
        Section("3 Consolidated financial statements", 3),
        Section("Notes", 3, ("3 Consolidated financial statements",)),
        Section("(1) Accounting policies", 3, ("3 Consolidated financial statements", "Notes")),
    ]


def test_body_font_size_is_the_most_used_one(report_pdf):
    blocks = list(read_blocks(report_pdf))
    sizes = {round(block.font_size, 1) for block in blocks}
    assert len(sizes) == 3  # header, page number, body
    assert body_font_size(blocks) == max(
        sizes, key=lambda size: sum(b.chars for b in blocks if b.font_size == size)
    )
    assert body_font_size([]) is None


def test_paragraphs_become_passages_with_page_and_section(report_pdf):
    passages = extract_passages(report_pdf, "ACME", 2025)
    assert [(p.page, p.section) for p in passages] == [
        (1, "1 To our investors"),
        (1, "1 To our investors"),
        (1, "1 To our investors"),
        (2, "2.1 Risks and opportunities"),
    ]
    assert all(p.company == "ACME" and p.year == 2025 for p in passages)

    first, second, right, risks = (p.text for p in passages)
    # Two paragraphs in one column stay apart, and so do the two columns.
    assert first.startswith("The past year was eventful") and first.endswith("environment.")
    assert second.startswith("Our shareholders benefit") and second.endswith("financial year.")
    assert right.startswith("In the right-hand column") and "eventful" not in right
    # A word hyphenated at the end of a line is joined again.
    assert "more expensive, and further trade barriers" in risks


def test_headers_headings_and_small_print_are_left_out(report_pdf):
    text = " ".join(p.text for p in extract_passages(report_pdf, "ACME", 2025))
    assert "running header" not in text
    assert "Main risks" not in text
    assert "8,000" not in text


def test_financial_statements_are_read_only_on_request(report_pdf):
    everything = extract_passages(report_pdf, "ACME", 2025, narrative_only=False)
    assert [p.page for p in everything] == [1, 1, 1, 2, 3]
    assert everything[-1].section == "(1) Accounting policies"


def test_report_without_bookmarks_is_read_in_full(report_pdf_without_bookmarks):
    assert read_sections(report_pdf_without_bookmarks) == []
    passages = extract_passages(report_pdf_without_bookmarks, "ACME", 2025)
    assert [p.page for p in passages] == [1, 1, 1, 2, 3]
    assert {p.section for p in passages} == {None}


def test_extraction_flag_is_read(report_pdf, restricted_report_pdf):
    assert extraction_allowed(report_pdf)
    assert not extraction_allowed(restricted_report_pdf)
    # The flag is not enforced by anything, so the text is still readable when asked for.
    assert len(extract_passages(restricted_report_pdf, "ACME", 2025)) == 4


def test_tightly_set_paragraphs_are_split_at_the_wider_gap(tight_report_pdf):
    passages = extract_passages(tight_report_pdf, "ACME", 2025)
    assert [p.text.split()[0] for p in passages] == ["Trends", "In"]
    assert passages[0].text.endswith("project scope.")
    assert "tariffs" in passages[1].text and "tariffs" not in passages[0].text
