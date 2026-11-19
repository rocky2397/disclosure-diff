import shutil

import pytest
from test_cli import StubJudge
from test_filings import FILING
from test_sec import URL_2024, URL_2025, FakeSec

from document_impact_analyzer.cli import main

# The later filing words the tariff risk anew and keeps the sentence on export controls.
FILING_2025 = FILING.replace(
    "Changes in trade policy, including <span>tariffs</span> and sanctions,&#160;could raise\n"
    "the cost of the materials we buy.",
    "Tariffs announced in April raised what we paid for imported steel by an estimated "
    "$40 million in the year.",
)


@pytest.fixture
def sec_site():
    assert FILING_2025 != FILING
    StubJudge.instances.clear()
    return FakeSec({URL_2024: FILING.encode(), URL_2025: FILING_2025.encode()})


def test_run_goes_from_a_ticker_to_the_report(tmp_path, sec_site, capsys):
    args = ["--data-dir", str(tmp_path), "run", "cvx", "2024", "2025"]
    assert main(args, judge_factory=StubJudge, sec_get=sec_site) == 0
    out = capsys.readouterr().out
    assert "CVX is CHEVRON CORP." in out and "Run 'dia extract'" not in out
    assert "CVX 2024: 5 passages from a Form 10-K filing, in 2 items" in out
    assert "CVX 2025, Protectionism: 2 passages found, 0 already judged, 2 to send" in out
    assert "  2024 Item 1A. Risk Factors -> 2025 Item 1A. Risk Factors\n1 pairs found." in out
    assert "0 new, 1 changed, 0 dropped, 1 unchanged." in out
    report = tmp_path / "output" / "CVX_protectionism_2024_2025.md"
    assert f"Written to {report}" in out
    assert "estimated $40 million" in report.read_text(encoding="utf-8")

    # A second run downloads nothing and sends nothing.
    sec_site.asked.clear()
    StubJudge.instances.clear()
    assert main(args, judge_factory=StubJudge, sec_get=sec_site) == 0
    out = capsys.readouterr().out
    assert sec_site.asked == [] and StubJudge.instances == []
    assert "The passages that wording could not match are paired already." in out
    assert "0 new, 1 changed, 0 dropped, 1 unchanged." in out


def test_run_dry_run_reads_the_reports_and_sends_nothing(tmp_path, sec_site, capsys):
    args = ["--data-dir", str(tmp_path), "run", "CVX", "2024", "2025", "--dry-run"]
    assert main(args, judge_factory=StubJudge, sec_get=sec_site) == 0
    out = capsys.readouterr().out
    assert "2 to send to claude-haiku-5-5." in out and "Nothing was sent." in out
    assert StubJudge.instances == []
    assert (tmp_path / "extracted" / "CVX_2025.jsonl").is_file()
    assert not (tmp_path / "judged").exists() and not (tmp_path / "output").exists()


@pytest.fixture
def acme(tmp_path, report_pdf):
    """A company that does not file with the SEC, with its two reports as PDFs."""
    folder = tmp_path / "reports" / "ACME"
    folder.mkdir(parents=True)
    shutil.copy(report_pdf, folder / "2024.pdf")
    shutil.copy(report_pdf, folder / "2025.pdf")
    StubJudge.instances.clear()
    return tmp_path


def test_run_uses_reports_that_are_in_the_data_folder(acme, capsys):
    site = FakeSec()
    args = ["--data-dir", str(acme), "run", "acme", "2024", "2025"]
    assert main(args, judge_factory=StubJudge, sec_get=site) == 0
    assert site.asked == []
    assert (acme / "output" / "ACME_protectionism_2024_2025.md").is_file()
    assert "Written to" in capsys.readouterr().out


def test_run_says_what_to_do_about_a_report_the_sec_does_not_have(acme, capsys):
    args = ["--data-dir", str(acme), "run", "ACME", "2023", "2024"]
    assert main(args, judge_factory=StubJudge, sec_get=FakeSec()) == 2
    err = capsys.readouterr().err
    assert "no company with the ticker ACME" in err
    assert "put its reports in the data folder as reports/ACME/<year>.pdf" in err
    assert StubJudge.instances == []


def test_run_stops_when_a_report_cannot_be_read(acme, restricted_report_pdf, capsys):
    shutil.copy(restricted_report_pdf, acme / "reports" / "ACME" / "2024.pdf")
    args = ["--data-dir", str(acme), "run", "ACME", "2024", "2025"]
    assert main(args, judge_factory=StubJudge) == 2
    captured = capsys.readouterr()
    assert "ACME 2024: not read. The publisher has switched off text extraction" in captured.out
    assert "ACME 2024 could not be read, for the reason given above" in captured.err
    assert StubJudge.instances == []
