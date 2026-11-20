"""Read an annual filing with the SEC, such as a 10-K, from its HTML.

A filing is one long web page without pages or bookmarks. Its paragraphs are the block
elements of the HTML, and its sections are the items every 10-K has to have: "Item 1A.
Risk Factors", "Item 7. Management's Discussion and Analysis" and so on. The headings are
found in the text, which works because their wording is prescribed.

Only the narrative items are kept by default, as for PDF reports: the business, the risk
factors, legal proceedings and the management discussion, not the financial statements
and not the items that only point to the proxy statement.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from disclosure_diff.ingest import Extraction
from disclosure_diff.passages import Passage, normalize

# A new one of these ends the paragraph before it.
_BLOCKS = frozenset(
    "address article aside blockquote body center dd div dl dt figure footer form h1 h2 h3 h4 "
    "h5 h6 header hr html li main nav ol p pre section table tbody td tfoot th thead tr ul".split()
)
# Nothing inside these is text of the filing. ix:header holds machine-readable data.
_SKIPPED = frozenset({"head", "script", "style", "title", "ix:header"})
_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta"})

_FORMS = ("10-K", "20-F", "40-F")
_FORM_ON_COVER = re.compile(r"\bFORM\s+(10-K|20-F|40-F)\b", re.IGNORECASE)
# "Item 1A. Risk Factors", "ITEM 7 —", "Items 1 and 2. Business and Properties"
_ITEM = re.compile(
    r"^items?\s+(\d{1,2}[A-C]?)(?:\s*(?:and|&|,)\s*\d{1,2}[A-C]?)*\b\s*[.:–—-]?\s*(.*)$",
    re.IGNORECASE,
)
_MAX_HEADING = 120

# The items of Form 10-K, with the titles used for citing. Filers vary the wording slightly.
ITEMS_10K = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for the Registrant's Common Equity",
    "6": "Reserved",
    "7": "Management's Discussion and Analysis",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements with Accountants",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "9C": "Disclosure Regarding Foreign Jurisdictions that Prevent Inspections",
    "10": "Directors, Executive Officers and Corporate Governance",
    "11": "Executive Compensation",
    "12": "Security Ownership",
    "13": "Certain Relationships and Related Transactions",
    "14": "Principal Accountant Fees and Services",
    "15": "Exhibits and Financial Statement Schedules",
    "16": "Form 10-K Summary",
}
# Some filers print a part of the 10-K away from its item: Chevron's management discussion
# and statements follow Item 14, each page headed with the title of its part. A short
# paragraph that starts with one of these titles therefore counts as the heading of the
# item it belongs to.
TITLES_10K = (
    ("management's discussion and analysis", "7"),
    ("quantitative and qualitative disclosures about market risk", "7A"),
    ("notes to the consolidated financial statements", "8"),
    ("notes to consolidated financial statements", "8"),
    ("report of independent registered public accounting firm", "8"),
    ("reports of independent registered public accounting firm", "8"),
)
# What a filing says before its first item: the cover page and, often, a cautionary note.
BEFORE_ITEMS = "Cover page and introduction"

# What counts as narrative, by form. A form that is not listed is read whole.
NARRATIVE_ITEMS = {
    "10-K": frozenset({"1", "1A", "1B", "1C", "2", "3", "7", "7A"}),
    # Key information with the risk factors, the company, the operating review, market risk.
    "20-F": frozenset({"3", "4", "4A", "5", "11"}),
}


# A filing whose narrative items hold less than this share of its text does not follow the
# item structure, and what the items do hold is not the filing.
_MIN_NARRATIVE_SHARE = 0.1
_MIN_PARAGRAPHS_TO_JUDGE = 200


class UnreadableFiling(ValueError):
    """The filing does not have the structure this module reads."""


class _Paragraphs(HTMLParser):
    """Collects the text of a filing paragraph by paragraph."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self.form: str | None = None
        self._text: list[str] = []
        self._breaks = 0
        self._hidden: str | None = None  # the tag whose content is being skipped
        self._hidden_depth = 0
        self._in_document_type = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._hidden:
            self._hidden_depth += tag == self._hidden
            return
        attributes = dict(attrs)
        style = (attributes.get("style") or "").replace(" ", "").lower()
        if tag in _SKIPPED or "display:none" in style:
            if tag not in _VOID:
                self._hidden, self._hidden_depth = tag, 1
            return
        if tag == "br":
            # One line break is a space. Two in a row separate paragraphs in older filings.
            self._breaks += 1
            if self._breaks >= 2:
                self._end_paragraph()
            else:
                self._text.append(" ")
        elif tag in _BLOCKS:
            self._end_paragraph()
        elif tag == "ix:nonnumeric" and attributes.get("name") == "dei:DocumentType":
            self._in_document_type = True

    def handle_endtag(self, tag: str) -> None:
        if self._hidden:
            self._hidden_depth -= tag == self._hidden
            if self._hidden_depth == 0:
                self._hidden = None
            return
        if tag in _BLOCKS:
            self._end_paragraph()
        elif tag == "ix:nonnumeric":
            self._in_document_type = False

    def handle_data(self, data: str) -> None:
        if self._hidden:
            return
        if self._in_document_type and self.form is None and data.strip().upper() in _FORMS:
            self.form = data.strip().upper()
        if data.strip():
            self._breaks = 0
        self._text.append(data)

    def close(self) -> None:
        super().close()
        self._end_paragraph()

    def _end_paragraph(self) -> None:
        text = normalize("".join(self._text).replace("\xa0", " "))
        self._text.clear()
        self._breaks = 0
        if text:
            self.paragraphs.append(text)


def read_paragraphs(html: str) -> tuple[list[str], str | None]:
    """The paragraphs of a filing in reading order, and its form type if it states one."""
    parser = _Paragraphs()
    parser.feed(html)
    parser.close()
    form = parser.form
    if form is None:
        for text in parser.paragraphs[:300]:
            found = _FORM_ON_COVER.search(text)
            if found:
                form = found.group(1).upper()
                break
    return parser.paragraphs, form


def item_heading(text: str) -> tuple[str, str] | None:
    """The item number and the title a paragraph gives, if the paragraph is an item heading."""
    if len(text) > _MAX_HEADING:
        return None
    found = _ITEM.match(text)
    if not found:
        return None
    return found.group(1).upper(), found.group(2).strip(" .:–—-")


def titled_item(text: str, form: str | None) -> str | None:
    """The item a paragraph is the title of, where a filer heads a part with its title only."""
    if form != "10-K" or len(text) > _MAX_HEADING:
        return None
    lowered = text.lower().replace("\u2019", "'")
    return next((item for title, item in TITLES_10K if lowered.startswith(title)), None)


def section_title(item: str, given: str, form: str | None) -> str:
    """How an item is cited: with the prescribed title for a 10-K, else with the filer's."""
    title = ITEMS_10K.get(item) if form == "10-K" else None
    title = title or given
    return f"Item {item}. {title}" if title else f"Item {item}"


def extract_filing(
    path: Path,
    company: str,
    year: int,
    *,
    narrative_only: bool = True,
    min_words: int = 8,
) -> Extraction:
    """Read a filing into passages, each with the item it stands in."""
    html = path.read_bytes().decode("utf-8", errors="replace")
    paragraphs, form = read_paragraphs(html)
    narrative = NARRATIVE_ITEMS.get(form or "")

    passages = []
    long_paragraphs = 0
    item: str | None = None
    section: str | None = BEFORE_ITEMS
    for text in paragraphs:
        heading = item_heading(text)
        if heading:
            item, given = heading
            section = section_title(item, given, form)
            continue
        titled = titled_item(text, form)
        if titled:
            item, section = titled, section_title(titled, "", form)
            continue
        if len(text.split()) < min_words:
            continue
        long_paragraphs += 1
        if narrative_only and narrative is not None and item is not None and item not in narrative:
            continue
        passages.append(Passage(company, year, 0, text, section, form=form))

    if (
        narrative_only
        and narrative is not None
        and long_paragraphs >= _MIN_PARAGRAPHS_TO_JUDGE
        and len(passages) < _MIN_NARRATIVE_SHARE * long_paragraphs
    ):
        raise UnreadableFiling(
            f"only {len(passages)} of {long_paragraphs} paragraphs stand under a narrative "
            f"item of Form {form}. The filing does not follow the item structure, as when a "
            "foreign company files its printed annual report as a 20-F."
        )
    return Extraction(passages, 0, [], [], [], [])
