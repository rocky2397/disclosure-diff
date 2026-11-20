"""Find candidate passages for a topic by phrase.

This step is meant to miss little and is allowed to return passages that turn out to be
off topic. A phrase matches whole words only, in any letter case, with or without hyphens,
and in its regular inflected forms: "tariff" finds "Tariffs", "anti-dumping" finds
"antidumping" and "anti dumping", "customs duty" finds "customs duties".
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache

from disclosure_diff.passages import Passage, normalize
from disclosure_diff.tables import looks_like_table
from disclosure_diff.topics import Topic

_JOIN_IN_WORD = r"[\s\-–]*"  # anti-dumping, anti dumping, antidumping
_JOIN_WORDS = r"[\s\-–]+"  # trade barrier, trade-barrier
_SUFFIX = r"(?:s|es|ed|ing)?"
# "AI" is easily set or read with a lowercase l in place of the capital I. A compound such
# as "Al-powered" is searched as "AI-powered" in any text; a name such as "Al-Khafji" has a
# capital after the hyphen and is left alone. In text read by OCR, where the misreading is
# common, the word "Al" on its own is searched as "AI" too. The replacement has the same
# length, so offsets still fit.
_AL_COMPOUND = re.compile(r"(?<![\w-])Al(?=-[a-z])")
_OCR_AI = re.compile(r"(?<![\w-])Al(?![\w-])")


@dataclass(frozen=True)
class Match:
    phrase: str
    start: int
    end: int


@dataclass(frozen=True)
class Candidate:
    passage: Passage
    matches: tuple[Match, ...]

    @property
    def phrases(self) -> tuple[str, ...]:
        """The distinct phrases found, in order of first appearance."""
        return tuple(dict.fromkeys(match.phrase for match in self.matches))


@cache
def compile_phrase(phrase: str) -> re.Pattern[str]:
    words = []
    for word in phrase.split():
        parts = [re.escape(part) for part in word.split("-") if part]
        words.append(_JOIN_IN_WORD.join(parts))
    last = words[-1]
    if last.endswith("y"):
        words[-1] = f"{last[:-1]}(?:y|ies)"
    else:
        words[-1] = last + _SUFFIX
    return re.compile(rf"(?<!\w){_JOIN_WORDS.join(words)}(?!\w)", re.IGNORECASE)


def find_matches(text: str, topic: Topic, *, ocr: bool = False) -> tuple[Match, ...]:
    """Phrase matches in ``text``. Offsets refer to ``normalize(text)``.

    ``ocr`` says the text was read by OCR, whose typical misreadings are then allowed for.
    """
    text = _AL_COMPOUND.sub("AI", normalize(text))
    if ocr:
        text = _OCR_AI.sub("AI", text)
    excluded = [
        found.span() for phrase in topic.exclude for found in compile_phrase(phrase).finditer(text)
    ]
    matches = []
    for phrase in topic.phrases:
        for found in compile_phrase(phrase).finditer(text):
            start, end = found.span()
            if any(start >= ex_start and end <= ex_end for ex_start, ex_end in excluded):
                continue
            matches.append(Match(phrase, start, end))
    return tuple(sorted(matches, key=lambda match: (match.start, match.end)))


def find_candidates(
    passages: Iterable[Passage], topic: Topic, *, skip_tables: bool = True
) -> list[Candidate]:
    """Passages that mention the topic, with the phrases found in each.

    A filing can repeat a paragraph word for word in several of its items. Such a
    paragraph is one statement, so it is found once, where it first stands.
    """
    candidates = []
    seen: set[str] = set()
    for passage in passages:
        if skip_tables and looks_like_table(passage.text):
            continue
        matches = find_matches(passage.text, topic, ocr=passage.ocr)
        if matches and passage.id not in seen:
            seen.add(passage.id)
            candidates.append(Candidate(passage, matches))
    return candidates
