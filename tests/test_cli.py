import shutil
from dataclasses import replace

import pytest

from disclosure_diff.cli import main
from disclosure_diff.judge import JudgeError
from disclosure_diff.judgements import (
    Concreteness,
    Direction,
    Judgement,
    Relevance,
    read_judgements,
)
from disclosure_diff.pairing import Pair
from disclosure_diff.passages import Passage, read_jsonl, write_jsonl


@pytest.fixture
def data_dir(tmp_path, report_pdf):
    folder = tmp_path / "reports" / "ACME"
    folder.mkdir(parents=True)
    for year in (2024, 2025):
        shutil.copy(report_pdf, folder / f"{year}.pdf")
    return tmp_path


def test_extract_writes_passages_and_skips_existing_ones(data_dir, capsys):
    assert main(["--data-dir", str(data_dir), "extract"]) == 0
    assert capsys.readouterr().out == "ACME 2024: 4 passages\nACME 2025: 4 passages\n"
    passages = list(read_jsonl(data_dir / "extracted" / "ACME_2024.jsonl"))
    assert len(passages) == 4 and passages[0].year == 2024

    assert main(["--data-dir", str(data_dir), "extract", "--company", "ACME"]) == 0
    assert "ACME 2024: already extracted, skipped" in capsys.readouterr().out

    assert main(["--data-dir", str(data_dir), "extract", "--force"]) == 0
    assert "ACME 2025: 4 passages" in capsys.readouterr().out


def test_extract_without_reports(tmp_path, capsys):
    assert main(["--data-dir", str(tmp_path), "extract"]) == 1
    assert "No reports found" in capsys.readouterr().err


def test_unplugged_drive_is_reported(tmp_path, capsys):
    assert main(["--data-dir", str(tmp_path / "gone"), "extract"]) == 2
    assert "plugged in" in capsys.readouterr().err


def test_changes_writes_a_report(data_dir, capsys):
    main(["--data-dir", str(data_dir), "extract"])
    capsys.readouterr()

    assert main(["--data-dir", str(data_dir), "changes", "ACME", "2024", "2025"]) == 0
    out = capsys.readouterr().out
    # Both years are the same PDF, so the one passage about tariffs is unchanged.
    assert out.startswith("0 new, 0 changed, 0 dropped, 1 unchanged.")
    report = data_dir / "output" / "ACME_protectionism_2024_2025.md"
    assert f"Written to {report}" in out
    assert report.read_text(encoding="utf-8").startswith("# ACME: Protectionism, 2024 to 2025")


def test_changes_needs_extracted_passages(data_dir, capsys):
    assert main(["--data-dir", str(data_dir), "changes", "ACME", "2024", "2025"]) == 2
    assert "Run 'disclosure-diff extract' first" in capsys.readouterr().err


class StubJudge:
    """Judges without the API. Fails on request to imitate an outage."""

    instances: list = []

    def __init__(self, *, model, effort, relevance=Relevance.COMPANY, fail=False):
        self.model, self.effort, self.relevance, self.fail = model, effort, relevance, fail
        self.input_tokens = self.output_tokens = 0
        self.judged = []
        self.neighbours = []
        self.paired = []
        self.scanned = []
        StubJudge.instances.append(self)

    def judge(self, passage, topic, neighbours=None):
        if self.fail:
            raise JudgeError("Could not reach the Anthropic API.")
        self.judged.append(passage.id)
        self.neighbours.append(neighbours)
        self.input_tokens += 700
        self.output_tokens += 90
        return Judgement(
            passage_id=passage.id,
            relevance=self.relevance,
            direction=Direction.RISK,
            concreteness=Concreteness.SPECIFIC,
            states_response=False,
            evidence="New tariffs on imported components",
            evidence_verified=True,
            model=self.model,
        )

    def scan(self, passage, topic):
        """Calls a passage about procurement about the company, and everything else off topic."""
        self.scanned.append(passage.id)
        missed = "procurement" in passage.text
        return Judgement(
            passage_id=passage.id,
            relevance=Relevance.COMPANY if missed else Relevance.OFF_TOPIC,
            direction=Direction.RISK if missed else Direction.NONE,
            concreteness=Concreteness.GENERIC,
            states_response=False,
            evidence=passage.text[:20],
            evidence_verified=True,
            model=self.model,
        )

    def pair(self, earlier, later, topic):
        """Pairs the first earlier passage with the last later one."""
        self.paired.append((list(earlier), list(later)))
        return [Pair(earlier[0].id, later[-1].id, self.model)]


@pytest.fixture
def extracted(data_dir, capsys):
    main(["--data-dir", str(data_dir), "extract"])
    capsys.readouterr()
    StubJudge.instances.clear()
    return data_dir


def test_judge_dry_run_sends_nothing(extracted, capsys):
    args = ["--data-dir", str(extracted), "judge", "ACME", "2025", "--dry-run"]
    assert main(args, judge_factory=StubJudge) == 0
    out = capsys.readouterr().out
    assert out == (
        "ACME 2025, Protectionism: 1 passages found, 0 already judged, "
        "1 to send to claude-haiku-5-5.\n"
        "A passage that comes back as background is sent once more, with the paragraphs "
        "before and after it.\n"
    )
    assert StubJudge.instances == []
    assert not (extracted / "judged").exists()


def test_judge_stores_judgements_and_does_not_repeat_them(extracted, capsys):
    args = ["--data-dir", str(extracted), "judge", "ACME", "2025"]
    assert main(args, judge_factory=StubJudge) == 0
    out = capsys.readouterr().out
    assert "  p. 2: company, risk, specific\n" in out
    assert "Tokens used: 700 in, 90 out." in out

    stored = read_judgements(extracted / "judged" / "ACME_2025_protectionism.jsonl")
    assert [j.relevance for j in stored.values()] == [Relevance.COMPANY]
    assert list(stored) == StubJudge.instances[0].judged

    assert main(args, judge_factory=StubJudge) == 0
    assert "1 already judged, 0 to send" in capsys.readouterr().out
    assert len(StubJudge.instances) == 1  # nothing left to judge, so no judge was built


def test_judge_sends_the_neighbouring_paragraphs_unless_told_not_to(extracted, capsys):
    # Give the one paragraph that is found a paragraph after it, in the same section.
    path = extracted / "extracted" / "ACME_2025.jsonl"
    passages = list(read_jsonl(path))
    found = next(p for p in passages if "New tariffs" in p.text)
    after = replace(found, text="This concerns the turbines we order for two wind farms.")
    passages.insert(passages.index(found) + 1, after)
    write_jsonl(passages, path)

    args = ["--data-dir", str(extracted), "judge", "ACME", "2025"]
    assert main(args, judge_factory=StubJudge) == 0
    (neighbours,) = StubJudge.instances[0].neighbours
    assert neighbours.before is None and neighbours.after == after
    capsys.readouterr()

    # Judged already, so only --again sends it once more. The later verdict is the one kept.
    again = lambda **options: StubJudge(relevance=Relevance.CONTEXT, **options)  # noqa: E731
    assert main([*args, "--again", "--no-context"], judge_factory=again) == 0
    out = capsys.readouterr().out
    assert "1 already judged, 1 to send to claude-haiku-5-5.\n" in out and "once more" not in out
    assert StubJudge.instances[1].neighbours == [None]
    stored = read_judgements(extracted / "judged" / "ACME_2025_protectionism.jsonl")
    assert [j.relevance for j in stored.values()] == [Relevance.CONTEXT]


def test_judge_failure_stops_with_a_message(extracted, capsys):
    args = ["--data-dir", str(extracted), "judge", "ACME", "2025", "--model", "claude-opus-5-5"]
    factory = lambda **options: StubJudge(fail=True, **options)  # noqa: E731
    assert main(args, judge_factory=factory) == 2
    captured = capsys.readouterr()
    assert "to send to claude-opus-5-5" in captured.out
    assert "Error: Could not reach the Anthropic API." in captured.err


def judge_year(data_dir, year, relevance=Relevance.COMPANY):
    factory = lambda **options: StubJudge(relevance=relevance, **options)  # noqa: E731
    assert (
        main(["--data-dir", str(data_dir), "judge", "ACME", str(year)], judge_factory=factory) == 0
    )


def test_changes_without_judgements_says_so(extracted, capsys):
    assert main(["--data-dir", str(extracted), "changes", "ACME", "2024", "2025"]) == 0
    assert "Not judged: this includes passages that mention the topic only in passing." in (
        capsys.readouterr().out
    )


def test_changes_keeps_only_passages_about_the_company(extracted, capsys):
    judge_year(extracted, 2024, Relevance.CONTEXT)
    judge_year(extracted, 2025, Relevance.CONTEXT)
    capsys.readouterr()
    changes = ["--data-dir", str(extracted), "changes", "ACME", "2024", "2025"]

    assert main(changes) == 0
    out = capsys.readouterr().out
    assert out.startswith("0 new, 0 changed, 0 dropped, 0 unchanged.")
    assert "Left out: 0 off-topic passages and 2 that mention the topic only as background." in out

    assert main(changes + ["--include-context", "--include-unchanged"]) == 0
    assert capsys.readouterr().out.startswith("0 new, 0 changed, 0 dropped, 1 unchanged.")
    report = (extracted / "output" / "ACME_protectionism_2024_2025.md").read_text(encoding="utf-8")
    assert "Judged by claude-haiku-5-5. Left out: 0 off-topic passages." in report
    assert "Background, not about the company." in report

    assert main(changes + ["--all-passages"]) == 0
    assert "Not judged" in capsys.readouterr().out


def test_changes_refuses_one_judged_and_one_unjudged_year(extracted, capsys):
    judge_year(extracted, 2025)
    capsys.readouterr()
    assert main(["--data-dir", str(extracted), "changes", "ACME", "2024", "2025"]) == 2
    assert "ACME 2025 is judged but 2024 is not. Run 'disclosure-diff judge ACME 2024'" in (
        capsys.readouterr().err
    )


def test_extract_leaves_restricted_pdfs_alone_unless_told_otherwise(
    tmp_path, restricted_report_pdf, capsys
):
    folder = tmp_path / "reports" / "ACME"
    folder.mkdir(parents=True)
    shutil.copy(restricted_report_pdf, folder / "2025.pdf")

    assert main(["--data-dir", str(tmp_path), "extract"]) == 0
    out = capsys.readouterr().out
    assert "ACME 2025: not read. The publisher has switched off text extraction" in out
    assert not (tmp_path / "extracted" / "ACME_2025.jsonl").exists()

    assert main(["--data-dir", str(tmp_path), "extract", "--allow-restricted"]) == 0
    assert "ACME 2025: 4 passages" in capsys.readouterr().out


def test_eval_freeze_and_eval(extracted, capsys):
    run = lambda *args, **kw: main(["--data-dir", str(extracted), *args], **kw)  # noqa: E731
    assert run("eval-freeze") == 2
    assert "No judged passages for protectionism" in capsys.readouterr().err
    assert run("eval") == 2
    assert "Run 'disclosure-diff eval-freeze' first" in capsys.readouterr().err

    judge_year(extracted, 2024)
    judge_year(extracted, 2025)
    capsys.readouterr()
    StubJudge.instances.clear()
    assert run("eval-freeze") == 0
    out = capsys.readouterr().out
    assert "2 passages frozen as the reference, with verdicts by claude-haiku-5-5." in out
    reference = extracted / "eval" / "reference_protectionism.jsonl"
    assert reference.is_file()
    assert run("eval-freeze") == 2
    assert "A reference is meant to stay fixed" in capsys.readouterr().err

    assert run("eval", "--dry-run", judge_factory=StubJudge) == 0
    out = capsys.readouterr().out
    assert "2 passages x 2 runs = 4 requests to claude-haiku-5-5.\n" in out
    # The sample reports have one paragraph per section, so there is nothing to send along.
    assert "holds no neighbouring paragraphs, so no passage gets a second look" in out
    assert StubJudge.instances == []
    assert run("eval", "--dry-run", "--no-context", judge_factory=StubJudge) == 0
    assert "second look" not in capsys.readouterr().out

    # The stub now calls every passage background, where the reference says company.
    factory = lambda **options: StubJudge(relevance=Relevance.CONTEXT, **options)  # noqa: E731
    assert run("eval", judge_factory=factory) == 0
    out = capsys.readouterr().out
    assert "4 answers, 0 failed attempts (not scored)." in out
    assert "about the company, background or off topic: 0 of 4 (0%)" in out
    assert "says what the company does about it: 4 of 4 (100%)" in out
    assert 'answering "company" every time would match the first line on 100%' in out
    assert "Same first answer in all 2 runs: 2 of 2 passages." in out
    assert "Evidence quoted word for word: 4 of 4." in out
    assert "Tokens: 2800 in, 360 out." in out
    assert "agreement with that model, not accuracy" in out
    assert "  ACME 2024 p. 2: reference company, got context, context" in out
    results = extracted / "output" / "eval" / "protectionism_claude-haiku-5-5_low.jsonl"
    assert len(results.read_text(encoding="utf-8").splitlines()) == 4


@pytest.fixture
def rewritten(tmp_path):
    """Two years in which one statement was written anew, one dropped and one added."""
    old_risk = Passage(
        "ACME",
        2024,
        64,
        "Should further import duties be imposed on solar modules, our projects in North "
        "America would become more expensive to build.",
    )
    new_risk = Passage(
        "ACME",
        2025,
        66,
        "Tariffs announced in April raise procurement costs for US photovoltaic plants by an "
        "estimated €40 million.",
    )
    old_other = Passage("ACME", 2024, 70, "Our embargo screening was extended to all suppliers.")
    new_other = Passage("ACME", 2025, 12, "Export controls delayed the delivery of two turbines.")
    (tmp_path / "extracted").mkdir()
    write_jsonl([old_risk, old_other], tmp_path / "extracted" / "ACME_2024.jsonl")
    write_jsonl([new_other, new_risk], tmp_path / "extracted" / "ACME_2025.jsonl")
    StubJudge.instances.clear()
    return tmp_path


def test_pair_matches_passages_that_were_written_anew(rewritten, capsys):
    run = lambda *args, **kw: main(["--data-dir", str(rewritten), *args], **kw)  # noqa: E731

    assert run("changes", "ACME", "2024", "2025") == 0
    out = capsys.readouterr().out
    assert out.startswith("2 new, 0 changed, 2 dropped, 0 unchanged.")
    assert "Run 'disclosure-diff pair ACME 2024 2025' to match those." in out

    assert run("pair", "ACME", "2024", "2025", "--dry-run", judge_factory=StubJudge) == 0
    out = capsys.readouterr().out
    assert "wording leaves 2 passages of 2024 and 2 of 2025 without a counterpart." in out
    assert "All of them go to claude-haiku-5-5 in one request." in out
    assert StubJudge.instances == [] and not (rewritten / "paired").exists()

    assert run("pair", "ACME", "2024", "2025", judge_factory=StubJudge) == 0
    out = capsys.readouterr().out
    assert "  2024 p. 64 -> 2025 p. 66\n1 pairs found." in out
    earlier, later = StubJudge.instances[0].paired[0]
    assert [p.page for p in earlier] == [64, 70] and [p.page for p in later] == [12, 66]
    assert (rewritten / "paired" / "ACME_2024_2025_protectionism.json").is_file()

    assert run("changes", "ACME", "2024", "2025") == 0
    out = capsys.readouterr().out
    assert out.startswith("1 new, 1 changed, 1 dropped, 0 unchanged.")
    assert "Written anew and paired by claude-haiku-5-5: 1 of the changed passages." in out
    assert "Run 'disclosure-diff pair" not in out
    report = (rewritten / "output" / "ACME_protectionism_2024_2025.md").read_text("utf-8")
    assert "Written anew; paired by claude-haiku-5-5. Wording similarity 0." in report
    assert report.index("p. 66") < report.index("p. 64")  # the later text is shown first


def test_changes_says_when_passages_were_not_part_of_the_pairing(rewritten, capsys):
    run = lambda *args, **kw: main(["--data-dir", str(rewritten), *args], **kw)  # noqa: E731
    assert run("pair", "ACME", "2024", "2025", judge_factory=StubJudge) == 0

    path = rewritten / "extracted" / "ACME_2025.jsonl"
    added = Passage("ACME", 2025, 80, "New sanctions stopped our gas purchases from one supplier.")
    write_jsonl([*read_jsonl(path), added], path)
    capsys.readouterr()
    assert run("changes", "ACME", "2024", "2025") == 0
    out = capsys.readouterr().out
    assert out.startswith("2 new, 1 changed, 1 dropped, 0 unchanged.")
    assert "Dropped or new passages the model has not seen for pairing: 1." in out


def test_pair_with_nothing_left_over_sends_nothing(extracted, capsys):
    args = ["--data-dir", str(extracted), "pair", "ACME", "2024", "2025"]
    assert main(args, judge_factory=StubJudge) == 0
    assert "Nothing to pair." in capsys.readouterr().out
    assert StubJudge.instances == []


def test_scan_reads_what_the_search_did_not_find(rewritten, capsys):
    run = lambda *args, **kw: main(["--data-dir", str(rewritten), *args], **kw)  # noqa: E731
    path = rewritten / "extracted" / "ACME_2025.jsonl"
    unfound = [
        Passage("ACME", 2025, 20, "Our procurement now depends on fewer countries of origin."),
        Passage("ACME", 2025, 21, "The dividend is to be raised again for the coming year."),
        Passage("ACME", 2025, 22, "Trade receivables 22,307 17 12,926 19 1,204 88 3,100 12"),
    ]
    write_jsonl([*read_jsonl(path), *unfound], path)

    assert run("scan", "ACME", "2025", "--dry-run", judge_factory=StubJudge) == 0
    out = capsys.readouterr().out
    # The table is neither searched nor scanned.
    assert "the search found 2 of 4 passages. Of the other 2, 0 are read already and 2 go to" in out
    assert StubJudge.instances == [] and not (rewritten / "scanned").exists()

    assert run("scan", "ACME", "2025", judge_factory=StubJudge) == 0
    out = capsys.readouterr().out
    assert "  p. 20: company\n" in out and "p. 21" not in out
    assert "calls 1 of them about the company and 0 background." in out
    assert len(StubJudge.instances[0].scanned) == 2
    report = (rewritten / "output" / "ACME_2025_protectionism_missed.md").read_text("utf-8")
    assert "## About the company" in report and "ACME Annual Report 2025, p. 20" in report
    assert "dividend" not in report and "so by this reading" not in report

    # Once the passages the search found are judged, the report says how many it found.
    assert run("judge", "ACME", "2025", judge_factory=StubJudge) == 0
    capsys.readouterr()
    assert run("scan", "ACME", "2025", judge_factory=StubJudge) == 0
    out = capsys.readouterr().out
    assert "2 are read already and 0 go to" in out
    assert "so by this reading the search found 2 of 3." in out
    assert len(StubJudge.instances) == 2  # the second scan had nothing to send


def test_an_interrupted_scan_keeps_what_it_has_read(rewritten, capsys):
    run = lambda *args, **kw: main(["--data-dir", str(rewritten), *args], **kw)  # noqa: E731
    path = rewritten / "extracted" / "ACME_2025.jsonl"
    more = [Passage("ACME", 2025, 30 + n, f"Paragraph number {n} on other things.") for n in (1, 2)]
    write_jsonl([*read_jsonl(path), *more], path)

    assert run("scan", "ACME", "2025", "--limit", "1", judge_factory=StubJudge) == 0
    out = capsys.readouterr().out
    assert "1 passages are still unread. Run the command again." in out
    assert run("scan", "ACME", "2025", judge_factory=StubJudge) == 0
    assert "1 are read already and 1 go to" in capsys.readouterr().out


def test_years_counts_report_by_report(extracted, capsys):
    run = lambda *args, **kw: main(["--data-dir", str(extracted), *args], **kw)  # noqa: E731
    folder = extracted / "reports" / "ACME"
    shutil.copy(folder / "2025.pdf", folder / "2023.pdf")  # in the folder, but not read
    judge_year(extracted, 2025)
    capsys.readouterr()

    assert run("years", "ACME") == 0
    out = capsys.readouterr().out
    assert "| 2023 | not read |" in out
    assert "| 2024 | 4 | 1 | not judged |" in out
    # One passage found, about the company, without a figure or a stated response.
    assert "| 2025 | 4 | 1 | 1 | 0 | 0 | 0 | 0 |" in out
    assert (extracted / "output" / "ACME_protectionism_years.md").is_file()

    assert run("years", "NOSUCH") == 2
    assert "No reports for NOSUCH" in capsys.readouterr().err


def test_a_year_without_any_passage_on_the_topic_can_be_compared(tmp_path, capsys):
    run = lambda *args, **kw: main(["--data-dir", str(tmp_path), *args], **kw)  # noqa: E731
    (tmp_path / "extracted").mkdir()
    earlier = Passage("ACME", 2022, 40, "The Covid-19 pandemic delayed two of our projects.")
    later = Passage("ACME", 2023, 41, "Two of our projects were completed on schedule.")
    write_jsonl([earlier], tmp_path / "extracted" / "ACME_2022.jsonl")
    write_jsonl([later], tmp_path / "extracted" / "ACME_2023.jsonl")

    assert run("judge", "ACME", "2022", "--topic", "covid", judge_factory=StubJudge) == 0
    assert run("judge", "ACME", "2023", "--topic", "covid", judge_factory=StubJudge) == 0
    assert "0 passages found, 0 already judged, 0 to send" in capsys.readouterr().out
    # Nothing was found in 2023, so there is no file of judgements for it, and none is needed.
    assert not (tmp_path / "judged" / "ACME_2023_covid.jsonl").exists()

    assert run("changes", "ACME", "2022", "2023", "--topic", "covid") == 0
    assert capsys.readouterr().out.startswith("0 new, 0 changed, 1 dropped, 0 unchanged.")


def test_a_drive_that_goes_away_during_a_run_is_reported(extracted, capsys, monkeypatch):
    def unplugged(path, judgement):
        raise FileNotFoundError(2, "No such file or directory", str(path))

    monkeypatch.setattr("disclosure_diff.cli.append_judgement", unplugged)
    args = ["--data-dir", str(extracted), "judge", "ACME", "2025"]
    assert main(args, judge_factory=StubJudge) == 2
    err = capsys.readouterr().err
    assert "a file could not be read or written" in err and "still plugged in" in err
