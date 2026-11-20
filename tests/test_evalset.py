import json

import pytest

from disclosure_diff import evalset
from disclosure_diff.judge import JudgeError
from disclosure_diff.judgements import Concreteness, Direction, Judgement, Relevance
from disclosure_diff.passages import Neighbours, Passage
from disclosure_diff.topics import PROTECTIONISM


def verdict(passage, relevance, *, model="reference-model", verified=True):
    return Judgement(
        passage_id=passage.id,
        relevance=relevance,
        direction=Direction.RISK if relevance is Relevance.COMPANY else Direction.NONE,
        concreteness=Concreteness.SPECIFIC,
        states_response=False,
        evidence="x",
        evidence_verified=verified,
        model=model,
    )


PASSAGES = [
    Passage("ACME", 2025, page, f"Passage number {page} about tariffs.") for page in (1, 2, 3)
]
REFERENCE = [Relevance.COMPANY, Relevance.COMPANY, Relevance.CONTEXT]
CASES = [evalset.make_case(p, verdict(p, r)) for p, r in zip(PASSAGES, REFERENCE, strict=True)]


class ScriptedJudge:
    """Answers from a script of relevance values, one per call. An exception is raised."""

    def __init__(self, script, *, model="test-model"):
        self.script = list(script)
        self.model = model
        self.input_tokens = self.output_tokens = 0
        self.neighbours = []

    def judge(self, passage, topic, neighbours=None):
        self.neighbours.append(neighbours)
        answer = self.script.pop(0)
        if isinstance(answer, Exception):
            raise answer
        self.input_tokens += 100
        self.output_tokens += 10
        return verdict(
            passage, answer, model=self.model, verified=answer is not Relevance.OFF_TOPIC
        )


def test_reference_round_trip(tmp_path):
    path = tmp_path / "eval" / "reference.jsonl"
    evalset.write_reference(CASES, path, frozen_on="2026-11-18")
    cases, frozen_on = evalset.read_reference(path)
    assert frozen_on == "2026-11-18"
    assert sorted(case.id for case in cases) == sorted(case.id for case in CASES)
    first = next(case for case in cases if case.id == CASES[0].id)
    assert first.passage == PASSAGES[0]
    assert first.reference["relevance"] == "company" and first.reference_model == "reference-model"
    assert first.label == "ACME 2025 p. 1"


def test_run_scores_answers_and_keeps_failures_apart():
    company, context, off = Relevance.COMPANY, Relevance.CONTEXT, Relevance.OFF_TOPIC
    # Run 1: right, wrong, right. Run 2: right, a failed request, off topic.
    judge = ScriptedJudge([company, context, context, company, JudgeError("rate limited"), off])
    attempts, failures = evalset.run(CASES, judge, PROTECTIONISM, runs=2, model="test-model")

    assert len(attempts) == 5 and [(f.run, f.reason) for f in failures] == [(2, "rate limited")]
    assert (attempts[0].input_tokens, attempts[0].output_tokens) == (100, 10)

    result = evalset.summarise(CASES, attempts, failures, runs=2)
    assert (result.cases, result.attempts, result.failures) == (3, 5, 1)
    assert result.matching["relevance"] == 3 and result.share["relevance"] == pytest.approx(0.6)
    assert (result.majority_answer, result.majority_share) == ("company", pytest.approx(2 / 3))
    assert result.reference_counts == {"company": 2, "context": 1}
    # Two passages were answered in both runs; one of them got two different answers.
    assert (result.repeated, result.stable) == (2, 1)
    assert result.evidence_verified == 4
    assert (result.input_tokens, result.output_tokens) == (500, 50)
    assert result.noise_points == pytest.approx(100 / 5**0.5)
    assert [(case.label, given) for case, given in result.differing] == [
        ("ACME 2025 p. 2", ["context"]),
        ("ACME 2025 p. 3", ["context", "off_topic"]),
    ]


def test_an_answer_from_another_model_is_not_scored():
    judge = ScriptedJudge([Relevance.COMPANY] * 3, model="fallback-model")
    attempts, failures = evalset.run(CASES, judge, PROTECTIONISM, runs=1, model="test-model")
    assert attempts == []
    assert {f.reason for f in failures} == {"answered by fallback-model, not by test-model"}


def test_a_failure_on_the_first_attempt_stops_the_run():
    judge = ScriptedJudge([JudgeError("No Anthropic credentials found.")])
    with pytest.raises(JudgeError, match="credentials"):
        evalset.run(CASES, judge, PROTECTIONISM, runs=2, model="test-model")


def test_too_many_failures_stop_the_run():
    judge = ScriptedJudge([Relevance.COMPANY] + [JudgeError("overloaded")] * 5)
    with pytest.raises(JudgeError, match="Stopped after 3 failed attempts"):
        evalset.run(CASES, judge, PROTECTIONISM, runs=2, model="test-model", max_failures=2)


def test_results_file_holds_every_answer_and_failure(tmp_path):
    judge = ScriptedJudge([Relevance.COMPANY, JudgeError("timeout"), Relevance.CONTEXT])
    attempts, failures = evalset.run(CASES, judge, PROTECTIONISM, runs=1, model="test-model")
    path = tmp_path / "out" / "results.jsonl"
    evalset.write_results(path, CASES, attempts, failures)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 3
    assert rows[0]["case"] == "ACME 2025 p. 1" and rows[0]["reference"]["relevance"] == "company"
    assert rows[-1] == {
        "case_id": CASES[1].id,
        "run": 1,
        "reason": "timeout",
        "case": "ACME 2025 p. 2",
        "failed": True,
    }


def test_neighbouring_paragraphs_are_frozen_and_sent_unless_switched_off(tmp_path):
    passage, after = PASSAGES[0], PASSAGES[1]
    case = evalset.make_case(passage, verdict(passage, Relevance.COMPANY), Neighbours(after=after))
    path = tmp_path / "reference.jsonl"
    evalset.write_reference([case, CASES[2]], path, frozen_on="2026-11-19")
    cases, _ = evalset.read_reference(path)
    cases.sort(key=lambda c: c.passage.page)  # the file is ordered by id
    assert [c.neighbours for c in cases] == [Neighbours(after=after), Neighbours()]

    judge = ScriptedJudge([Relevance.COMPANY] * 4)
    evalset.run(cases, judge, PROTECTIONISM, runs=1, model="test-model")
    evalset.run(cases, judge, PROTECTIONISM, runs=1, model="test-model", context=False)
    assert judge.neighbours == [Neighbours(after=after), Neighbours(), None, None]


def test_a_reference_frozen_before_neighbours_were_kept_still_loads(tmp_path):
    path = tmp_path / "reference.jsonl"
    evalset.write_reference(CASES, path, frozen_on="2026-11-18")
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        del row["before"], row["after"]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    cases, _ = evalset.read_reference(path)
    assert len(cases) == 3 and not any(case.neighbours for case in cases)
