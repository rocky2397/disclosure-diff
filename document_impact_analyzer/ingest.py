"""Read an annual report PDF into passages.

Sections come from the PDF's bookmarks. Text comes from pdfminer's layout analysis, which
groups lines into blocks and keeps the columns of a multi-column page apart. A block
becomes a passage when it is set in the report's body font size and is long enough to be a
paragraph, which leaves out running headers, page numbers, chart labels and footnotes.

Text that exists only as pixels is not in the PDF's text: a scanned page, or a picture of
a paragraph placed on a page that also has ordinary text. Such pages are counted, and with
``ocr=True`` they are rendered and read by Tesseract. Text that OCR finds where the PDF
already has text is dropped, so nothing is read twice.

Some PDFs carry text that cannot be decoded: their fonts do not say which characters the
glyphs stand for, and every letter comes out as a code such as "(cid:12)". Such pages are
treated like pages without text.

Known limits: a paragraph that continues in the next column or on the next page is split
in two, and a report without bookmarks gets no sections.
"""

from __future__ import annotations

import io
import logging
import re
import statistics
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pdfminer.high_level import extract_pages
from pdfminer.layout import (
    LAParams,
    LTChar,
    LTContainer,
    LTImage,
    LTTextBoxHorizontal,
    LTTextLineHorizontal,
)
from pypdf import PdfReader
from pypdf.constants import UserAccessPermissions

from document_impact_analyzer.passages import Passage, normalize
from document_impact_analyzer.sections import Section, clean_title, is_narrative, section_for_page

# Lines up to one line height apart belong to one block. Body text in annual reports is
# set with generous leading, and pdfminer's default of 0.5 puts every line in its own block.
_LAYOUT = LAParams(line_margin=1.0)

# A page with fewer characters than this has no text to speak of: a scan, a cover, a divider.
MIN_PAGE_CHARS = 50
# A page whose pictures cover at least this share of it may hold text inside a picture.
# A picture of one paragraph takes up well under a tenth of a page.
LARGE_IMAGE_SHARE = 0.05
# Tesseract reports font sizes in whole points and up to a point too small: 10.2 pt text
# came back as 9, and 8.5 pt text as 8 or 9. OCR text is therefore compared with the most
# common OCR size when there is enough OCR text to tell, and only otherwise, and more
# loosely, with the size of the PDF's own text.
_OCR_SIZE_TOLERANCE = 1.0
_OCR_SIZE_TOLERANCE_BORROWED = 1.25
_OCR_MIN_CHARS_FOR_OWN_SIZE = 2000
_OCR_DPI = 300

# What pdfminer writes for a glyph whose character it cannot determine.
_UNDECODED = re.compile(r"\(cid:\d+\)")
# A page counts as undecodable when at least this share of its glyphs came out that way.
# Readable reports have next to none. In Chevron's 2025 report the worst pages are all
# codes, and the best still have 17%, with the rest of their letters mapped to wrong ones.
UNDECODED_SHARE = 0.02

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Block:
    """A block of text on a page with the font size most of it is set in."""

    page: int
    text: str
    font_size: float
    chars: int
    # Left, bottom, right, top in points, measured from the bottom left of the page.
    box: Box = (0.0, 0.0, 0.0, 0.0)
    ocr: bool = False


@dataclass(frozen=True)
class PageScan:
    """What one pass over a page found."""

    page: int
    blocks: list[Block]
    # Share of the page covered by pictures, between 0 and 1.
    image_share: float

    @property
    def chars(self) -> int:
        return sum(block.chars for block in self.blocks)

    @property
    def undecodable(self) -> bool:
        """True when much of the page's text is glyph codes instead of characters."""
        codes = sum(len(_UNDECODED.findall(block.text)) for block in self.blocks)
        return self.chars >= MIN_PAGE_CHARS and codes / self.chars >= UNDECODED_SHARE


@dataclass(frozen=True)
class Extraction:
    passages: list[Passage]
    pages: int
    # Pages with almost no text in the PDF.
    textless_pages: list[int] = field(default_factory=list)
    # Pages whose text cannot be decoded. Their text is left out.
    undecodable_pages: list[int] = field(default_factory=list)
    # Pages that have text and also a large picture.
    image_pages: list[int] = field(default_factory=list)
    # Pages OCR was run on.
    ocr_pages: list[int] = field(default_factory=list)


class OcrUnavailable(RuntimeError):
    """OCR was asked for but its software is not installed."""


# pdfminer logs a warning for every pass over a PDF that restricts text extraction. The
# restriction is checked once, up front, by extraction_allowed().
logging.getLogger("pdfminer.pdfpage").setLevel(logging.ERROR)


def extraction_allowed(path: Path) -> bool:
    """False when the PDF's publisher has switched off copying and extracting its content.

    This is a permission setting inside the file, the one that greys out "copy" in a PDF
    viewer. Nothing technical enforces it, so whether to read such a file anyway is left to
    the person running the tool.
    """
    reader = PdfReader(str(path))
    if not reader.is_encrypted:
        return True
    return bool(reader.user_access_permissions & UserAccessPermissions.EXTRACT)


def read_sections(path: Path) -> list[Section]:
    """The report's bookmarks as sections, in page order. Empty if it has none."""
    reader = PdfReader(str(path))
    sections: list[Section] = []

    def walk(items, ancestors: tuple[str, ...]) -> None:
        # pypdf gives the children of a bookmark as a list right after that bookmark.
        previous = None
        for item in items:
            if isinstance(item, list):
                walk(item, ancestors + ((previous,) if previous else ()))
                continue
            title = clean_title(item.title or "")
            page = reader.get_destination_page_number(item)
            if title and page is not None and page >= 0:
                sections.append(Section(title, page + 1, ancestors))
            previous = title or previous

    walk(reader.outline, ())
    # Stable sort: bookmarks on the same page keep their order, the more specific one last.
    return sorted(sections, key=lambda section: section.start_page)


def _paragraphs(box: LTTextBoxHorizontal) -> list[list[LTTextLineHorizontal]]:
    """The lines of a layout box, split where the gap between two lines is clearly wider.

    The layout analysis joins lines that are up to one line height apart. That suits
    reports set with generous leading, where a paragraph break is a blank line. In a
    report with tight leading it joins a whole column: in Chevron's reports the lines of
    a paragraph are 2.6 pt apart and paragraphs 7.7 pt, both under one line height.
    """
    lines = sorted(
        (line for line in box if isinstance(line, LTTextLineHorizontal)),
        key=lambda line: -line.y1,
    )
    if len(lines) < 3:
        return [lines] if lines else []
    gaps = [upper.y0 - lower.y1 for upper, lower in zip(lines, lines[1:], strict=False)]
    usual = statistics.median(gaps)
    wider = usual + 0.3 * statistics.median(line.height for line in lines)
    paragraphs = [[lines[0]]]
    for line, gap in zip(lines[1:], gaps, strict=False):
        if gap > wider:
            paragraphs.append([])
        paragraphs[-1].append(line)
    return paragraphs


def _text_blocks(layout, page_number: int, *, ocr: bool = False) -> list[Block]:
    blocks = []
    for box in layout:
        if not isinstance(box, LTTextBoxHorizontal):
            continue
        for lines in _paragraphs(box):
            sizes: Counter[float] = Counter()
            for line in lines:
                for char in line:
                    if isinstance(char, LTChar):
                        sizes[round(char.size, 1)] += 1
            text = normalize("".join(line.get_text() for line in lines))
            if not sizes or not text:
                continue
            bounds = (
                min(line.x0 for line in lines),
                min(line.y0 for line in lines),
                max(line.x1 for line in lines),
                max(line.y1 for line in lines),
            )
            size = sizes.most_common(1)[0][0]
            blocks.append(Block(page_number, text, size, sum(sizes.values()), bounds, ocr))
    return blocks


def _image_share(layout) -> float:
    """Share of the page covered by pictures. Overlapping pictures are counted twice."""
    page_area = layout.width * layout.height
    if not page_area:
        return 0.0

    def area(item) -> float:
        if isinstance(item, LTImage):
            left, bottom, right, top = item.bbox
            width = min(right, layout.width) - max(left, 0)
            height = min(top, layout.height) - max(bottom, 0)
            return max(width, 0) * max(height, 0)
        if isinstance(item, LTContainer):
            return sum(area(child) for child in item)
        return 0.0

    return min(area(layout) / page_area, 1.0)


def read_pages(path: Path) -> Iterator[PageScan]:
    """Text blocks and picture coverage of every page, with 1-based page numbers."""
    for page_number, layout in enumerate(extract_pages(str(path), laparams=_LAYOUT), start=1):
        yield PageScan(page_number, _text_blocks(layout, page_number), _image_share(layout))


def read_blocks(path: Path) -> Iterator[Block]:
    """Every text block of the PDF in reading order."""
    for scan in read_pages(path):
        yield from scan.blocks


def body_font_size(blocks: Iterable[Block]) -> float | None:
    """The font size most of the characters are set in."""
    chars_by_size: Counter[float] = Counter()
    for block in blocks:
        chars_by_size[block.font_size] += block.chars
    return chars_by_size.most_common(1)[0][0] if chars_by_size else None


def _overlap_share(box: Box, others: Sequence[Box]) -> float:
    """Share of ``box`` that is covered by the other boxes."""
    left, bottom, right, top = box
    area = (right - left) * (top - bottom)
    if area <= 0:
        return 0.0
    covered = 0.0
    for o_left, o_bottom, o_right, o_top in others:
        width = min(right, o_right) - max(left, o_left)
        height = min(top, o_top) - max(bottom, o_bottom)
        if width > 0 and height > 0:
            covered += width * height
    return min(covered / area, 1.0)


def ocr_blocks(
    path: Path,
    page_numbers: Sequence[int],
    existing: Mapping[int, Sequence[Block]],
    *,
    language: str = "eng",
) -> list[Block]:
    """Text that Tesseract reads on the given pages and that the PDF's own text lacks.

    Each page is rendered as a picture and read. Tesseract returns its result as a PDF
    with an invisible text layer in the same coordinates as the page, which goes through
    the same layout analysis as ordinary text. A block at least half covered by text the
    PDF already has is that same text read again, and is dropped.
    """
    if not page_numbers:
        return []
    try:
        import pypdfium2
        import pytesseract
    except ImportError as error:
        raise OcrUnavailable("OCR needs extra packages: pip install -e '.[ocr]'") from error

    blocks: list[Block] = []
    document = pypdfium2.PdfDocument(str(path))
    try:
        for page_number in page_numbers:
            image = document[page_number - 1].render(scale=_OCR_DPI / 72).to_pil()
            try:
                result = pytesseract.image_to_pdf_or_hocr(
                    image, extension="pdf", lang=language, config=f"--dpi {_OCR_DPI}"
                )
            except pytesseract.TesseractNotFoundError as error:
                raise OcrUnavailable(
                    "OCR needs the Tesseract program, for example: brew install tesseract"
                ) from error
            known = [block.box for block in existing.get(page_number, ())]
            for layout in extract_pages(io.BytesIO(result), laparams=_LAYOUT):
                for block in _text_blocks(layout, page_number, ocr=True):
                    if _overlap_share(block.box, known) < 0.5:
                        blocks.append(block)
    finally:
        document.close()
    return blocks


def extract(
    path: Path,
    company: str,
    year: int,
    *,
    narrative_only: bool = True,
    min_words: int = 8,
    size_tolerance: float = 0.3,
    ocr: bool = False,
) -> Extraction:
    """Read a report into passages and say which pages may hold text as pictures."""
    sections = read_sections(path)
    scans = list(read_pages(path))
    undecodable = [scan.page for scan in scans if scan.undecodable]
    readable = [scan for scan in scans if not scan.undecodable]
    native = [block for scan in readable for block in scan.blocks]
    body = body_font_size(native)

    textless = [scan.page for scan in readable if scan.chars < MIN_PAGE_CHARS]
    with_images = [
        scan.page
        for scan in readable
        if scan.chars >= MIN_PAGE_CHARS and scan.image_share >= LARGE_IMAGE_SHARE
    ]

    recognised: list[Block] = []
    ocr_pages: list[int] = []
    if ocr:
        ocr_pages = sorted(textless + undecodable + with_images)
        # Undecodable text is not text the PDF "already has", so it must not hide OCR text.
        existing = {scan.page: scan.blocks for scan in readable}
        recognised = ocr_blocks(path, ocr_pages, existing)

    if sum(block.chars for block in recognised) >= _OCR_MIN_CHARS_FOR_OWN_SIZE or body is None:
        ocr_body, ocr_tolerance = body_font_size(recognised), _OCR_SIZE_TOLERANCE
    else:
        ocr_body, ocr_tolerance = body, _OCR_SIZE_TOLERANCE_BORROWED

    passages = []
    for block in sorted(native + recognised, key=lambda block: block.page):
        target, tolerance = (ocr_body, ocr_tolerance) if block.ocr else (body, size_tolerance)
        if target is None or abs(block.font_size - target) > tolerance:
            continue
        if len(block.text.split()) < min_words:
            continue
        section = section_for_page(sections, block.page)
        if narrative_only and not is_narrative(section, sections):
            continue
        passages.append(
            Passage(
                company,
                year,
                block.page,
                block.text,
                section.title if section else None,
                ocr=block.ocr,
            )
        )
    return Extraction(passages, len(scans), textless, undecodable, with_images, ocr_pages)


def extract_passages(
    path: Path,
    company: str,
    year: int,
    *,
    narrative_only: bool = True,
    min_words: int = 8,
    size_tolerance: float = 0.3,
    ocr: bool = False,
) -> list[Passage]:
    """Paragraphs of the report as passages with page and section."""
    return extract(
        path,
        company,
        year,
        narrative_only=narrative_only,
        min_words=min_words,
        size_tolerance=size_tolerance,
        ocr=ocr,
    ).passages
