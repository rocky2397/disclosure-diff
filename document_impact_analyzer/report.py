"""Render year-over-year changes as Markdown.

Findings are quoted from the report with the page they are on. Nothing is summarised or
paraphrased, so every statement can be checked against the source.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from document_impact_analyzer.changes import Change, Status
from document_impact_analyzer.judgements import Judgement, Relevance
from document_impact_analyzer.passages import Passage, normalize
from document_impact_analyzer.topics import Topic


def quote(passage: Passage, *, max_chars: int = 700) -> str:
    """The passage as a Markdown block quote with its citation, cut at a word boundary."""
    text = normalize(passage.text)
    if len(text) > max_chars:
        cut = text[:max_chars]
        if not text[max_chars].isspace():  # the cut fell inside a word
            cut = cut.rsplit(" ", 1)[0]
        text = cut.rstrip() + " […]"
    return f"> {text}\n>\n> {passage.citation}"


def describe(judgement: Judgement) -> str:
    """A judgement in words, for the line under a quote."""
    if judgement.relevance is Relevance.CONTEXT:
        return "Background, not about the company."
    if judgement.relevance is Relevance.OFF_TOPIC:
        return "Off topic."
    direction = {
        "risk": "Risk",
        "opportunity": "Opportunity",
        "both": "Risk and opportunity",
        "none": "Descriptive",
    }[judgement.direction.value]
    text = f"{direction}, {judgement.concreteness.value}"
    if judgement.states_response:
        text += ", says what the company does about it"
    return text + "."


def _key_sentence(judgement: Judgement, passage: Passage, max_chars: int) -> str:
    """The judge's evidence, where the quote above it does not show it.

    That is the case when the quote was shortened, and when the evidence stands in the
    paragraph before or after the passage.
    """
    evidence = normalize(judgement.evidence)
    if not judgement.evidence_verified:
        return ""
    if judgement.evidence_from in ("before", "after"):
        return (
            f" The link to the company is stated in the paragraph {judgement.evidence_from} "
            f"it: \u201c{evidence}\u201d"
        )
    if evidence.casefold() in normalize(passage.text)[:max_chars].casefold():
        return ""
    return f" Key sentence, after the cut: \u201c{evidence}\u201d"


def render_changes(
    company: str,
    topic: Topic,
    year_before: int,
    year_after: int,
    changes: Sequence[Change],
    *,
    judgements: Mapping[str, Judgement] | None = None,
    notes: Sequence[str] = (),
    include_unchanged: bool = False,
    max_chars: int = 700,
) -> str:
    """A Markdown report of what changed between two annual reports.

    With ``judgements`` (by passage id), each quote is followed by what the judge decided
    about it. Without them, a passage is only flagged when it contains an amount.
    """
    judgements = judgements or {}
    by_status = {status: [c for c in changes if c.status is status] for status in Status}

    summary = (
        f"{len(by_status[Status.NEW])} new, {len(by_status[Status.CHANGED])} changed, "
        f"{len(by_status[Status.DROPPED])} dropped, {len(by_status[Status.UNCHANGED])} unchanged."
    )
    if not judgements:
        quantified = sum(1 for c in changes if c.newly_quantified)
        summary += (
            f" {quantified} new or changed passages state an amount that was not there before."
        )
    lines = [f"# {company}: {topic.name}, {year_before} to {year_after}", "", summary, ""]
    for note in notes:
        lines += [note, ""]
    if not changes:
        lines += [f"No passages about {topic.name.lower()} were found in either report.", ""]

    def judged(passage: Passage) -> list[str]:
        judgement = judgements.get(passage.id)
        if not judgement:
            return []
        return [describe(judgement) + _key_sentence(judgement, passage, max_chars), ""]

    if by_status[Status.NEW]:
        lines += [f"## New in {year_after}", ""]
        for change in by_status[Status.NEW]:
            lines += [quote(change.after, max_chars=max_chars), ""]
            lines += judged(change.after)
            if change.after.id not in judgements and change.newly_quantified:
                lines += ["States an amount.", ""]

    if by_status[Status.CHANGED]:
        lines += [f"## Changed from {year_before} to {year_after}", ""]
        for change in by_status[Status.CHANGED]:
            note = f"Similarity {change.similarity:.2f}."
            if change.paired_by:
                note = f"Written anew; paired by {change.paired_by}. Wording similarity " + (
                    f"{change.similarity:.2f}."
                )
            after, before = judgements.get(change.after.id), judgements.get(change.before.id)
            if after:
                note = f"{describe(after)}{_key_sentence(after, change.after, max_chars)} {note}"
                if before and before.concreteness is not after.concreteness:
                    note += f" In {year_before} this was {before.concreteness.value}."
            elif change.newly_quantified:
                note += f" States an amount that the {year_before} text did not."
            lines += [
                f"**{year_after}**",
                "",
                quote(change.after, max_chars=max_chars),
                "",
                f"**{year_before}**",
                "",
                quote(change.before, max_chars=max_chars),
                "",
                note,
                "",
            ]

    if by_status[Status.DROPPED]:
        lines += [f"## Dropped after {year_before}", ""]
        for change in by_status[Status.DROPPED]:
            lines += [quote(change.before, max_chars=max_chars), ""]
            lines += judged(change.before)

    if include_unchanged and by_status[Status.UNCHANGED]:
        lines += ["## Unchanged", ""]
        for change in by_status[Status.UNCHANGED]:
            lines += [quote(change.after, max_chars=max_chars), ""]
            lines += judged(change.after)

    return "\n".join(lines).rstrip() + "\n"


def render_missed(
    company: str,
    topic: Topic,
    year: int,
    *,
    scanned: int,
    found: int,
    found_company: int | None,
    missed: Sequence[tuple[Passage, Judgement]],
    background: Sequence[tuple[Passage, Judgement]],
    model: str,
    max_chars: int = 700,
) -> str:
    """What the phrase search did not find, according to the judge.

    ``missed`` are passages the judge calls about the company, ``background`` those it
    calls background. ``found_company`` is how many of the passages the search did find
    are about the company, or ``None`` if they are not judged.
    """
    lines = [f"# {company} {year}: {topic.name}, passages the search did not find", ""]
    summary = (
        f"The phrase search found {found} passages. {model} read the other {scanned} and "
        f"calls {len(missed)} of them about the company and {len(background)} background."
    )
    if found_company is not None and found_company + len(missed):
        total = found_company + len(missed)
        summary += (
            f" Of the passages found, {found_company} are about the company, so by this "
            f"reading the search found {found_company} of {total}."
        )
    lines += [summary, ""]
    lines += [
        "This is one model's reading, not a count of errors. Read the passages below "
        "before adding search phrases.",
        "",
    ]
    for title, items in (("About the company", missed), ("Background", background)):
        if not items:
            continue
        lines += [f"## {title}", ""]
        for passage, judgement in sorted(items, key=lambda item: item[0].page):
            lines += [quote(passage, max_chars=max_chars), ""]
            lines += [describe(judgement) + _key_sentence(judgement, passage, max_chars), ""]
    return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True)
class YearRow:
    """What one report says about a topic, in numbers."""

    year: int
    # Paragraphs read from the report, or ``None`` if the report has not been read.
    read: int | None = None
    found: int = 0
    judged: bool = False
    company: int = 0
    # Of the passages about the company: those that state a figure, and those that say
    # what the company does about the topic.
    quantified: int = 0
    response: int = 0
    background: int = 0
    off_topic: int = 0


def render_years(company: str, topic: Topic, rows: Sequence[YearRow]) -> str:
    """A table with one line per report, to see a topic appear, grow and fade."""
    lines = [
        f"# {company}: {topic.name} by year",
        "",
        "| Year | Paragraphs read | Found | About the company | With a figure "
        "| Says what the company does | Background | Off topic |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in sorted(rows, key=lambda row: row.year):
        if row.read is None:
            cells = ["not read"] + [""] * 6
        elif not row.judged:
            cells = [row.read, row.found, "not judged", "", "", "", ""]
        else:
            cells = [
                row.read,
                row.found,
                row.company,
                row.quantified,
                row.response,
                row.background,
                row.off_topic,
            ]
        lines.append(f"| {row.year} | " + " | ".join(str(cell) for cell in cells) + " |")
    lines += [
        "",
        "The counts depend on how long a report is and how it is divided into paragraphs, "
        "so read them next to the paragraphs read.",
    ]
    return "\n".join(lines) + "\n"
