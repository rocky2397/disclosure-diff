"""Sections of an annual report, taken from the PDF's bookmarks.

A passage is only worth searching when it comes from the narrative part of the report: the
letter to investors, the management report with its risk and outlook chapters. The
financial statements, their notes, the auditor's report and the back matter are not.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_WHITESPACE = re.compile(r"\s+")
_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)\s+")

# Matched against the title without its number, in lower case.
_NOT_NARRATIVE = re.compile(
    r"financial statements|income statement|statement of income|comprehensive income"
    r"|recognized income and expenses|balance sheet|cash flow statement|statement of cash flows"
    r"|changes in equity|^notes\b|list of shareholdings|^boards\b"
    r"|auditor|assurance report|responsibility statement|declaration of the board"
    r"|takeover|^contents$|^at a glance$|five-year overview|financial highlights"
    r"|^imprint$|financial calendar|^glossary$"
)


@dataclass(frozen=True)
class Section:
    title: str
    start_page: int
    # Titles of the bookmarks this one is nested in, outermost first.
    ancestors: tuple[str, ...] = ()

    @property
    def number(self) -> str | None:
        """The leading section number, such as "2.9", if the title has one."""
        found = _NUMBER.match(self.title)
        return found.group(1) if found else None

    @property
    def name(self) -> str:
        """The title without its number."""
        return _NUMBER.sub("", self.title)


def clean_title(title: str) -> str:
    return _WHITESPACE.sub(" ", title).strip()


def section_for_page(sections: Sequence[Section], page: int) -> Section | None:
    """The most specific section that has started by ``page``.

    A page on which a new section begins is assigned to that section, although the text
    above its heading may still belong to the previous one.
    """
    current = None
    for section in sorted(sections, key=lambda s: s.start_page):
        if section.start_page > page:
            break
        current = section
    return current


def chapter_of(sections: Sequence[Section], section: Section) -> Section | None:
    """The top-level chapter of a numbered section: "2.9 …" belongs to "2 …".

    The numbering is used because bookmark nesting is not reliable. In RWE's 2025 report
    half of chapter 2 sits at the top level of the bookmark tree.
    """
    if not section.number or "." not in section.number:
        return None
    top = section.number.split(".")[0]
    return next((s for s in sections if s.number == top), None)


def is_narrative(section: Section | None, sections: Sequence[Section] = ()) -> bool:
    """False for financial statements, notes, audit reports and back matter.

    A section is judged by its own title, by its chapter as given by the numbering, and by
    the bookmarks it is nested in. The nesting matters for reports without numbering: in
    E.ON's reports the notes are bookmarks such as "(1) Summary of Significant Accounting
    Policies" under "Notes".

    A page without a known section counts as narrative, so that a report without bookmarks
    is still searched in full.
    """
    if section is None:
        return True
    chapter = chapter_of(sections, section)
    titles = [section.name, *section.ancestors] + ([chapter.name] if chapter else [])
    return not any(_NOT_NARRATIVE.search(_NUMBER.sub("", title).lower()) for title in titles)
