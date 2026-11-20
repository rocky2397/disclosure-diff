"""Check the judge against a frozen set of earlier verdicts.

Nobody labels passages by hand in this project, so there is no ground truth. What there is
instead is a reference: the verdicts stored at one point in time, frozen together with the
text of their passages. Judging those passages again, with another model, another effort
level or a changed prompt, and counting how many answers match tells you whether a change
altered anything and whether a cheaper setup is equivalent.

It does not tell you whether the judge is right. A reference made by one model rewards
answering like that model.

Three things are measured without any reference at all: whether the evidence is quoted
word for word, whether the judge gives the same answer when asked again, and how many
tokens a run uses.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from disclosure_diff.judge import Judge, JudgeError
from disclosure_diff.judgements import Judgement
from disclosure_diff.passages import Neighbours, Passage
from disclosure_diff.topics import Topic

# The four answers a verdict consists of, with the wording used in the summary.
ANSWERS = {
    "relevance": "about the company, background or off topic",
    "direction": "risk, opportunity, both or neither",
    "concreteness": "generic, specific or quantified",
    "states_response": "says what the company does about it",
}


def answers_of(judgement: Judgement) -> dict[str, str | bool]:
    return {
        "relevance": judgement.relevance.value,
        "direction": judgement.direction.value,
        "concreteness": judgement.concreteness.value,
        "states_response": judgement.states_response,
    }


@dataclass(frozen=True)
class Case:
    """One passage with the verdict it had when the reference was frozen."""

    passage: Passage
    reference: dict[str, str | bool]
    # The model whose verdict this is. Scores against it reward agreeing with that model.
    reference_model: str
    # The paragraphs printed before and after the passage, frozen with it.
    neighbours: Neighbours = Neighbours()

    @property
    def id(self) -> str:
        return self.passage.id

    @property
    def label(self) -> str:
        return f"{self.passage.company} {self.passage.year} {self.passage.where}"


def make_case(passage: Passage, judgement: Judgement, neighbours: Neighbours | None = None) -> Case:
    return Case(passage, answers_of(judgement), judgement.model, neighbours or Neighbours())


def _row(passage: Passage | None) -> dict | None:
    return asdict(passage) if passage else None


def _passage(row: dict | None) -> Passage | None:
    return Passage(**row) if row else None


def write_reference(cases: Sequence[Case], path: Path, *, frozen_on: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for case in sorted(cases, key=lambda c: (c.passage.company, c.passage.year, c.id)):
            row = {
                "passage": asdict(case.passage),
                "reference": case.reference,
                "reference_model": case.reference_model,
                "frozen_on": frozen_on,
                "before": _row(case.neighbours.before),
                "after": _row(case.neighbours.after),
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_reference(path: Path) -> tuple[list[Case], str]:
    """The frozen cases and the date they were frozen on."""
    cases, frozen_on = [], ""
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            frozen_on = row.get("frozen_on", frozen_on)
            # References frozen before neighbours were kept have neither key.
            neighbours = Neighbours(_passage(row.get("before")), _passage(row.get("after")))
            passage = Passage(**row["passage"])
            cases.append(Case(passage, row["reference"], row["reference_model"], neighbours))
    return cases, frozen_on


@dataclass(frozen=True)
class Attempt:
    """One answer to one case in one run."""

    case_id: str
    run: int
    answers: dict[str, str | bool]
    evidence_verified: bool
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class Failure:
    """An attempt that produced no answer to score. It is not counted as a wrong answer."""

    case_id: str
    run: int
    reason: str


@dataclass
class Summary:
    cases: int
    runs: int
    attempts: int
    failures: int
    # Per answer: matching attempts, and the share of scored attempts that match.
    matching: dict[str, int] = field(default_factory=dict)
    share: dict[str, float] = field(default_factory=dict)
    # Agreement on relevance if every passage got the reference's most common answer.
    majority_answer: str = ""
    majority_share: float = 0.0
    reference_counts: dict[str, int] = field(default_factory=dict)
    # Cases answered in every run, and those of them with the same relevance each time.
    repeated: int = 0
    stable: int = 0
    evidence_verified: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    # Half-width, in percentage points, below which a difference in share is noise.
    noise_points: float = 0.0
    # Cases whose relevance differs from the reference in at least one run.
    differing: list[tuple[Case, list[str]]] = field(default_factory=list)


def summarise(
    cases: Sequence[Case], attempts: Sequence[Attempt], failures: Sequence[Failure], runs: int
) -> Summary:
    by_case: dict[str, list[Attempt]] = {}
    for attempt in attempts:
        by_case.setdefault(attempt.case_id, []).append(attempt)
    reference = {case.id: case.reference for case in cases}

    summary = Summary(len(cases), runs, len(attempts), len(failures))
    for answer in ANSWERS:
        matching = sum(1 for a in attempts if a.answers[answer] == reference[a.case_id][answer])
        summary.matching[answer] = matching
        summary.share[answer] = matching / len(attempts) if attempts else 0.0

    counts = Counter(str(case.reference["relevance"]) for case in cases)
    summary.reference_counts = dict(counts)
    if counts:
        summary.majority_answer, most = counts.most_common(1)[0]
        summary.majority_share = most / len(cases)

    for case in cases:
        answered = sorted(by_case.get(case.id, []), key=lambda a: a.run)
        given = [str(a.answers["relevance"]) for a in answered]
        if len(answered) == runs and runs > 1:
            summary.repeated += 1
            summary.stable += len(set(given)) == 1
        if any(answer != case.reference["relevance"] for answer in given):
            summary.differing.append((case, given))

    summary.evidence_verified = sum(1 for a in attempts if a.evidence_verified)
    summary.input_tokens = sum(a.input_tokens for a in attempts)
    summary.output_tokens = sum(a.output_tokens for a in attempts)
    if attempts:
        # For a share near one half, about 1 / sqrt(n) on each side.
        summary.noise_points = 100 / math.sqrt(len(attempts))
    return summary


def write_results(
    path: Path, cases: Sequence[Case], attempts: Sequence[Attempt], failures: Sequence[Failure]
) -> None:
    """Every answer and every failure of a run, so a surprising number can be traced."""
    labels = {case.id: case.label for case in cases}
    reference = {case.id: case.reference for case in cases}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for attempt in attempts:
            row = asdict(attempt) | {
                "case": labels[attempt.case_id],
                "reference": reference[attempt.case_id],
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        for failure in failures:
            row = asdict(failure) | {"case": labels[failure.case_id], "failed": True}
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def run(
    cases: Sequence[Case],
    judge: Judge,
    topic: Topic,
    *,
    runs: int,
    model: str,
    context: bool = True,
    on_attempt: Callable[[Case, int], None] | None = None,
    max_failures: int = 10,
) -> tuple[list[Attempt], list[Failure]]:
    """Judge every case ``runs`` times, with its neighbouring paragraphs unless ``context``
    is off.

    An attempt that fails, or that another model answered, is recorded as a failure and
    not scored: a broken request is not a wrong answer. A failure on the very first
    attempt, or more than ``max_failures`` in all, stops the run, because then the setup
    is at fault.
    """
    attempts: list[Attempt] = []
    failures: list[Failure] = []
    for number in range(1, runs + 1):
        for case in cases:
            tokens_in = getattr(judge, "input_tokens", 0)
            tokens_out = getattr(judge, "output_tokens", 0)
            try:
                judgement = judge.judge(case.passage, topic, case.neighbours if context else None)
            except JudgeError as error:
                if not attempts and not failures:
                    raise
                failures.append(Failure(case.id, number, str(error)))
            else:
                if judgement.model != model:
                    reason = f"answered by {judgement.model}, not by {model}"
                    failures.append(Failure(case.id, number, reason))
                else:
                    attempts.append(
                        Attempt(
                            case.id,
                            number,
                            answers_of(judgement),
                            judgement.evidence_verified,
                            getattr(judge, "input_tokens", 0) - tokens_in,
                            getattr(judge, "output_tokens", 0) - tokens_out,
                        )
                    )
            if len(failures) > max_failures:
                raise JudgeError(f"Stopped after {len(failures)} failed attempts.")
            if on_attempt:
                on_attempt(case, number)
    return attempts, failures
