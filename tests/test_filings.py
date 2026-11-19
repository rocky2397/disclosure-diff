import pytest

from document_impact_analyzer.cli import main
from document_impact_analyzer.filings import (
    UnreadableFiling,
    extract_filing,
    item_heading,
    read_paragraphs,
    section_title,
)
from document_impact_analyzer.passages import read_jsonl

FILING = """<html><head><title>acme-20241231</title><style>p {margin: 0}</style></head><body>
<div style="display:none"><ix:header><ix:hidden>
<ix:nonNumeric name="dei:EntityCentralIndexKey">0000012345</ix:nonNumeric>
hidden words that must never show up in any paragraph of the filing at all
</ix:hidden></ix:header></div>
<div>UNITED STATES SECURITIES AND EXCHANGE COMMISSION</div>
<div>FORM <ix:nonNumeric name="dei:DocumentType">10-K</ix:nonNumeric></div>
<table>
<tr><td>Item 1.</td><td>Business</td><td>3</td></tr>
<tr><td>Item 1A.</td><td>Risk Factors</td><td>20</td></tr>
<tr><td>Item 8.</td><td>Financial Statements and Supplementary Data</td><td>60</td></tr>
</table>
<div><span style="font-weight:bold">Item 1. Business</span></div>
<div>ACME is an integrated energy company with operations in many countries of the world.</div>
<div><span>ITEM 1A. RISK FACTORS</span></div>
<div>Changes in trade policy, including <span>tariffs</span> and sanctions,&#160;could raise
the cost of the materials we buy.</div>
<table><tr><td>&#8226;</td>
<td>export controls may delay the delivery of equipment that our projects depend on;</td>
</tr></table>
<p>First paragraph of an older filing, about our supply chain and its many dependencies.<br>
<br>Second paragraph after two line breaks, about the same supply chain and its risks.</p>
<div>Item 8. Financial Statements and Supplementary Data</div>
<div>Trade receivables are measured at amortised cost, and the expected loss is estimated.</div>
<table><tr><td>Revenue</td><td>1,200</td><td>1,100</td></tr></table>
</body></html>"""


@pytest.fixture
def filing(tmp_path):
    path = tmp_path / "2024.htm"
    path.write_text(FILING, encoding="utf-8")
    return path


def test_paragraphs_come_from_the_block_elements_and_hidden_data_is_left_out():
    paragraphs, form = read_paragraphs(FILING)
    assert form == "10-K"
    assert "UNITED STATES SECURITIES AND EXCHANGE COMMISSION" in paragraphs
    assert not any("hidden words" in text or "acme-20241231" in text for text in paragraphs)
    # Inline tags and a non-breaking space do not split a paragraph.
    assert (
        "Changes in trade policy, including tariffs and sanctions, could raise the cost of "
        "the materials we buy." in paragraphs
    )
    # Two line breaks in a row do.
    first = "First paragraph of an older filing, about our supply chain and its many dependencies."
    assert first in paragraphs


def test_the_form_is_read_from_the_cover_when_it_is_not_tagged():
    _, form = read_paragraphs("<body><p>ANNUAL REPORT</p><p>Form 20-F</p></body>")
    assert form == "20-F"
    assert read_paragraphs("<body><p>Some other document.</p></body>")[1] is None


@pytest.mark.parametrize(
    ("text", "heading"),
    [
        ("Item 1A. Risk Factors", ("1A", "Risk Factors")),
        ("ITEM 7. MANAGEMENT’S DISCUSSION", ("7", "MANAGEMENT’S DISCUSSION")),
        ("Items 1 and 2. Business and Properties", ("1", "Business and Properties")),
        ("Item 1A.", ("1A", "")),
        ("Itemized deductions were higher than last year in most segments.", None),
        ("See Item 1A for a discussion of these risks.", None),
        ("Item 1A describes the risks that could affect us. " * 4, None),
    ],
)
def test_item_headings_are_recognised(text, heading):
    assert item_heading(text) == heading


def test_a_10k_item_is_cited_with_its_prescribed_title():
    assert section_title("1A", "RISK FACTORS", "10-K") == "Item 1A. Risk Factors"
    assert section_title("1A", "", "10-K") == "Item 1A. Risk Factors"
    # Another form keeps the title the filer gives.
    assert section_title("3", "Key Information", "20-F") == "Item 3. Key Information"
    assert section_title("3", "", "20-F") == "Item 3"


def test_a_filing_becomes_passages_with_their_item_and_without_the_financial_statements(filing):
    result = extract_filing(filing, "ACME", 2024)
    assert [(p.section, p.text[:28]) for p in result.passages] == [
        ("Item 1. Business", "ACME is an integrated energy"),
        ("Item 1A. Risk Factors", "Changes in trade policy, inc"),
        ("Item 1A. Risk Factors", "export controls may delay th"),
        ("Item 1A. Risk Factors", "First paragraph of an older "),
        ("Item 1A. Risk Factors", "Second paragraph after two l"),
    ]
    assert all(p.form == "10-K" and p.page == 0 and not p.ocr for p in result.passages)
    assert result.passages[1].citation == "ACME Form 10-K 2024, Item 1A. Risk Factors"

    everything = extract_filing(filing, "ACME", 2024, narrative_only=False)
    assert everything.passages[-1].section == "Item 8. Financial Statements and Supplementary Data"


def test_extract_reads_a_filing_next_to_pdf_reports(tmp_path, filing, capsys):
    folder = tmp_path / "data" / "reports" / "ACME"
    folder.mkdir(parents=True)
    filing.rename(folder / "2024.htm")

    assert main(["--data-dir", str(tmp_path / "data"), "extract"]) == 0
    assert "ACME 2024: 5 passages from a Form 10-K filing, in 2 items" in capsys.readouterr().out
    stored = list(read_jsonl(tmp_path / "data" / "extracted" / "ACME_2024.jsonl"))
    assert stored[1].form == "10-K" and stored[1].section == "Item 1A. Risk Factors"


def test_a_part_printed_away_from_its_item_is_found_by_its_title(tmp_path):
    # As in Chevron's 10-K: Item 7 only points to the discussion, which follows Item 14.
    path = tmp_path / "2024.htm"
    path.write_text(
        """<body><div>FORM 10-K</div>
        <div>This report contains forward-looking statements about our plans and results.</div>
        <div>Item 7. Management's Discussion and Analysis</div>
        <div>The index to the discussion is presented in the financial table of contents.</div>
        <div>Item 14. Principal Accountant Fees and Services</div>
        <div>Information on accountant fees is incorporated by reference from the proxy.</div>
        <div>Management’s Discussion and Analysis of Financial Condition and Results</div>
        <div>Tariffs announced during the year raised the cost of materials for our projects.</div>
        <div>Notes to the Consolidated Financial Statements</div>
        <div>Inventories are stated at cost, using a last-in, first-out method for crude oil.</div>
        <div>Management’s Discussion and Analysis of Financial Condition and Results</div>
        <div>Higher interest rates increased the cost of financing our capital programme.</div>
        </body>""",
        encoding="utf-8",
    )
    result = extract_filing(path, "ACME", 2024)
    assert [(p.section, p.text.split()[0]) for p in result.passages] == [
        ("Cover page and introduction", "This"),
        ("Item 7. Management's Discussion and Analysis", "The"),
        ("Item 7. Management's Discussion and Analysis", "Tariffs"),
        ("Item 7. Management's Discussion and Analysis", "Higher"),
    ]


def test_a_filing_without_the_item_structure_is_refused_and_not_half_read(tmp_path, capsys):
    # As BP's 20-F: the printed annual report, with the items only in a table at the end.
    body = "".join(
        f"<div>Paragraph {n} of the annual report, which has no item headings at all.</div>"
        for n in range(250)
    )
    table = "<div>Item 3. Key Information</div><div>See the pages named in the guide above.</div>"
    folder = tmp_path / "reports" / "ACME"
    folder.mkdir(parents=True)
    path = folder / "2024.htm"
    path.write_text(f"<body><div>Form 20-F</div><div>Item 17</div>{body}{table}</body>", "utf-8")

    with pytest.raises(UnreadableFiling, match="only 1 of 251 paragraphs stand under a narrative"):
        extract_filing(path, "ACME", 2024)
    assert len(extract_filing(path, "ACME", 2024, narrative_only=False).passages) == 251

    assert main(["--data-dir", str(tmp_path), "extract"]) == 0
    assert "ACME 2024: not read, because only 1 of 251 paragraphs" in capsys.readouterr().out
    assert not (tmp_path / "extracted" / "ACME_2024.jsonl").exists()
