from document_impact_analyzer.judgements import (
    Concreteness,
    Direction,
    Judgement,
    Relevance,
    append_judgement,
    evidence_is_verbatim,
    judgements_path,
    read_judgements,
)
from document_impact_analyzer.settings import DataDir


def judgement(passage_id="abc123", relevance=Relevance.COMPANY):
    return Judgement(
        passage_id=passage_id,
        relevance=relevance,
        direction=Direction.RISK,
        concreteness=Concreteness.SPECIFIC,
        states_response=True,
        evidence="additional tariffs could be introduced – „Zölle“",
        evidence_verified=True,
        model="claude-opus-5-5",
    )


def test_json_round_trip_keeps_enums_and_unicode():
    line = judgement().to_json()
    assert '"relevance": "company"' in line and "„Zölle“" in line
    assert Judgement.from_json(line) == judgement()


def test_evidence_must_appear_in_the_passage():
    passage = "The increase in tariff barriers caused\nanother risk to materialise."
    assert evidence_is_verbatim("caused another risk to MATERIALISE.", passage)
    assert not evidence_is_verbatim("tariffs cost us €120 million", passage)
    assert not evidence_is_verbatim("  ", passage)


def test_store_appends_and_the_latest_judgement_wins(tmp_path):
    data = DataDir(tmp_path)
    path = judgements_path(data, "RWE", 2025, "protectionism")
    assert path == tmp_path / "judged" / "RWE_2025_protectionism.jsonl"
    assert read_judgements(path) == {}

    append_judgement(path, judgement("a"))
    append_judgement(path, judgement("b"))
    append_judgement(path, judgement("a", Relevance.CONTEXT))

    stored = read_judgements(path)
    assert sorted(stored) == ["a", "b"]
    assert stored["a"].relevance is Relevance.CONTEXT


def test_judgements_stored_before_neighbours_existed_still_load():
    line = judgement().to_json()
    old = line.replace(', "evidence_from": "passage", "saw_neighbours": false', "")
    assert old != line and Judgement.from_json(old) == judgement()
