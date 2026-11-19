import importlib.util
import shutil

import pytest

from document_impact_analyzer import ingest
from document_impact_analyzer.cli import main
from document_impact_analyzer.ingest import (
    Block,
    OcrUnavailable,
    PageScan,
    _overlap_share,
    extract,
)

# These tests need the Tesseract program and the packages of the "ocr" extra.
needs_ocr = pytest.mark.skipif(
    shutil.which("tesseract") is None
    or importlib.util.find_spec("pypdfium2") is None
    or importlib.util.find_spec("pytesseract") is None,
    reason="Tesseract or the ocr extra is not installed",
)


def test_overlap_share():
    box = (0.0, 0.0, 10.0, 10.0)
    assert _overlap_share(box, [(0.0, 0.0, 10.0, 5.0)]) == 0.5
    assert _overlap_share(box, [(0.0, 0.0, 5.0, 5.0), (5.0, 5.0, 10.0, 10.0)]) == 0.5
    assert _overlap_share(box, [(20.0, 20.0, 30.0, 30.0)]) == 0.0
    assert _overlap_share((0.0, 0.0, 0.0, 0.0), [box]) == 0.0


def test_a_scanned_report_has_no_text_and_says_so(scanned_report_pdf):
    result = extract(scanned_report_pdf, "ACME", 2025)
    assert result.passages == []
    assert (result.pages, result.textless_pages, result.ocr_pages) == (3, [1, 2, 3], [])


@needs_ocr
def test_ocr_reads_a_scanned_report(scanned_report_pdf):
    result = extract(scanned_report_pdf, "ACME", 2025, ocr=True)
    assert result.ocr_pages == [1, 2, 3]
    assert result.passages and all(passage.ocr for passage in result.passages)

    by_page = {
        page: " ".join(p.text for p in result.passages if p.page == page) for page in (1, 2, 3)
    }
    assert "The past year was eventful and also very successful" in by_page[1]
    assert "tariffs on imported components" in by_page[2]
    assert "further trade barriers may delay deliveries" in by_page[2]
    assert "expected credit loss" in by_page[3]
    # The running header is set smaller than the body text and stays out.
    assert "running header" not in " ".join(by_page.values())
    # The two columns of the first page are still separate paragraphs.
    assert len([p for p in result.passages if p.page == 1]) == 3
    assert result.passages[0].citation.endswith("read by OCR")


def test_a_picture_on_a_page_with_text_is_noticed(mixed_page_pdf):
    result = extract(mixed_page_pdf, "ACME", 2025)
    assert [p.text[:36] for p in result.passages] == ["This paragraph is ordinary text in t"]
    assert (result.textless_pages, result.image_pages) == ([], [1])


@needs_ocr
def test_ocr_adds_the_picture_text_without_repeating_the_ordinary_text(mixed_page_pdf):
    result = extract(mixed_page_pdf, "ACME", 2025, ocr=True)
    ordinary = [p for p in result.passages if not p.ocr]
    from_picture = [p for p in result.passages if p.ocr]

    assert len(ordinary) == 1 and len(from_picture) == 1
    assert "export controls on turbine components delayed two of our projects" in (
        from_picture[0].text
    )
    assert "ordinary text" not in from_picture[0].text
    assert sum("New tariffs on imported" in p.text for p in result.passages) == 1


@needs_ocr
def test_missing_tesseract_is_explained(scanned_report_pdf, monkeypatch):
    import pytesseract

    monkeypatch.setattr(pytesseract.pytesseract, "tesseract_cmd", "no-such-tesseract")
    with pytest.raises(OcrUnavailable, match="needs the Tesseract program"):
        extract(scanned_report_pdf, "ACME", 2025, ocr=True)


@needs_ocr
def test_extract_command_with_and_without_ocr(tmp_path, scanned_report_pdf, capsys):
    folder = tmp_path / "reports" / "ACME"
    folder.mkdir(parents=True)
    shutil.copy(scanned_report_pdf, folder / "2025.pdf")

    assert main(["--data-dir", str(tmp_path), "extract"]) == 0
    out = capsys.readouterr().out
    assert "ACME 2025: 0 passages" in out
    assert "3 pages have no readable text and 0 have text plus pictures. Pass --ocr" in out

    assert main(["--data-dir", str(tmp_path), "extract", "--ocr", "--force"]) == 0
    out = capsys.readouterr().out
    assert "of them read by OCR (3 pages checked)" in out and "Pass --ocr" not in out


def undecodable_block(page):
    """What pdfminer returns for a page set in fonts without a character map."""
    text = "".join(f"(cid:{n % 90})" for n in range(400))
    return Block(page, text, 10.0, 400, (40.0, 40.0, 800.0, 560.0))


def test_page_with_glyph_codes_counts_as_undecodable():
    assert PageScan(1, [undecodable_block(1)], 0.0).undecodable
    table = Block(1, "Trade receivables 22,307 17 12,926 19 " * 10, 10.0, 300)
    assert not PageScan(1, [table], 0.0).undecodable
    # A stray code, such as a bullet the font does not name, is not enough.
    prose = Block(1, "New tariffs raised our costs considerably. " * 20 + "(cid:3)", 10.0, 800)
    assert not PageScan(1, [prose], 0.0).undecodable
    # A page that is one sixth codes is: its other letters are mapped to wrong characters.
    partly = Block(1, "VWXYZ[W]W^_ a_^^]Zb " * 20 + "(cid:10)" * 80, 10.0, 480)
    assert PageScan(1, [partly], 0.0).undecodable


@pytest.fixture
def undecodable_report(scanned_report_pdf, monkeypatch):
    """The scanned sample report, read as if every page also had undecodable text on it.

    That is what Chevron's 2025 report looks like to the tool: the pages show ordinary
    text, but the text in the file is glyph codes.
    """

    def read_pages(path):
        for page in (1, 2, 3):
            yield PageScan(page, [undecodable_block(page)], 0.0)

    monkeypatch.setattr(ingest, "read_pages", read_pages)
    return scanned_report_pdf


def test_undecodable_text_is_left_out_and_reported(undecodable_report):
    result = extract(undecodable_report, "ACME", 2025)
    assert result.passages == []
    assert (result.undecodable_pages, result.textless_pages) == ([1, 2, 3], [])


@needs_ocr
def test_ocr_reads_pages_whose_text_cannot_be_decoded(undecodable_report):
    result = extract(undecodable_report, "ACME", 2025, ocr=True)
    assert result.ocr_pages == [1, 2, 3]
    text = " ".join(passage.text for passage in result.passages)
    # The undecodable block covers the whole page, yet it does not hide what OCR reads.
    assert "tariffs on imported components" in text and "(cid:" not in text
    assert all(passage.ocr for passage in result.passages)


def test_extract_command_says_when_text_cannot_be_decoded(undecodable_report, tmp_path, capsys):
    folder = tmp_path / "reports" / "ACME"
    folder.mkdir(parents=True)
    shutil.copy(undecodable_report, folder / "2025.pdf")
    assert main(["--data-dir", str(tmp_path), "extract"]) == 0
    out = capsys.readouterr().out
    assert "3 pages have no readable text" in out
    assert "On 3 of those pages the PDF has text that cannot be decoded" in out
