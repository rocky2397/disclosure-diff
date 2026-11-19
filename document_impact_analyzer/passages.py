"""A passage is one paragraph of an annual report, with enough context to cite it."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

_HYPHEN_BREAK = re.compile(r"(\w)-\s*\n\s*(\w)")
_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Undo line-break hyphenation and collapse whitespace, as PDF text needs."""
    return _WHITESPACE.sub(" ", _HYPHEN_BREAK.sub(r"\1\2", text)).strip()


@dataclass(frozen=True)
class Passage:
    company: str
    year: int
    page: int
    text: str
    section: str | None = None
    # The text was read from a picture by OCR, so it may contain misread characters.
    ocr: bool = False
    # For a filing with the SEC, its form type, such as "10-K". Such a filing has no pages,
    # so ``page`` is 0 and the passage is cited by its section.
    form: str | None = None

    @property
    def id(self) -> str:
        """Stable identifier, used to join hand labels to passages."""
        key = f"{self.company}|{self.year}|{self.page}|{normalize(self.text)}"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]

    @property
    def document(self) -> str:
        """The kind of report and its year."""
        return f"Form {self.form} {self.year}" if self.form else f"Annual Report {self.year}"

    @property
    def where(self) -> str:
        """The place in the report: the page, or the section where there are no pages."""
        if self.page:
            return f"p. {self.page}"
        return self.section or "no section"

    @property
    def citation(self) -> str:
        source = f"{self.company} {self.document}, {self.where}"
        return f"{source}, read by OCR" if self.ocr else source


@dataclass(frozen=True)
class Neighbours:
    """The paragraphs printed directly before and after a passage, where there are any."""

    before: Passage | None = None
    after: Passage | None = None

    def __bool__(self) -> bool:
        return self.before is not None or self.after is not None


def find_neighbours(passages: Sequence[Passage]) -> dict[str, Neighbours]:
    """For every passage of a report, by id, the passages printed just before and after it.

    ``passages`` is one report in reading order. A neighbour has to be in the same section
    and on the same or the adjoining page, so that the first paragraph of a chapter is not
    read together with the end of the previous one.
    """

    def beside(passage: Passage, other: Passage) -> Passage | None:
        close = other.section == passage.section and abs(other.page - passage.page) <= 1
        return other if close else None

    found = {}
    for index, passage in enumerate(passages):
        before = beside(passage, passages[index - 1]) if index else None
        after = beside(passage, passages[index + 1]) if index + 1 < len(passages) else None
        found[passage.id] = Neighbours(before, after)
    return found


def write_jsonl(passages: Iterable[Passage], path: Path) -> int:
    """Write passages one JSON object per line. Returns how many were written."""
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for passage in passages:
            handle.write(json.dumps(asdict(passage), ensure_ascii=False) + "\n")
            count += 1
    return count


def read_jsonl(path: Path) -> Iterator[Passage]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield Passage(**json.loads(line))
