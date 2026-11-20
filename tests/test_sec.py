import json

import pytest

from disclosure_diff import sec
from disclosure_diff.cli import main
from disclosure_diff.library import find_reports
from disclosure_diff.settings import DataDir

TICKERS = {"0": {"cik_str": 93410, "ticker": "CVX", "title": "CHEVRON CORP"}}
SUBMISSIONS = {
    "filings": {
        "recent": {
            "form": ["8-K", "10-K", "10-K/A", "10-Q", "10-K"],
            "reportDate": ["2026-03-01", "2025-12-31", "2024-12-31", "2025-09-30", "2024-12-31"],
            "filingDate": ["2026-03-02", "2026-02-20", "2025-04-01", "2025-11-05", "2025-02-21"],
            "accessionNumber": ["0-26-1", "0000093410-26-000010", "0-25-9", "0-25-7", "0-25-5"],
            "primaryDocument": [
                "a.htm",
                "cvx-20251231.htm",
                "amend.htm",
                "q.htm",
                "cvx-20241231.htm",
            ],
        }
    }
}
URL_2025 = "https://www.sec.gov/Archives/edgar/data/93410/000009341026000010/cvx-20251231.htm"
URL_2024 = "https://www.sec.gov/Archives/edgar/data/93410/0255/cvx-20241231.htm"


class FakeSec:
    """Stands in for the SEC: answers from a table and remembers what was asked."""

    def __init__(self, extra=None):
        self.pages = {
            sec.TICKERS_URL: json.dumps(TICKERS).encode(),
            sec.SUBMISSIONS_URL.format(cik=93410): json.dumps(SUBMISSIONS).encode(),
            URL_2025: b"<html><body><p>Form 10-K 2025</p></body></html>",
            URL_2024: b"<html><body><p>Form 10-K 2024</p></body></html>",
        } | (extra or {})
        self.asked = []

    def __call__(self, url):
        self.asked.append(url)
        if url not in self.pages:
            raise sec.SecError(f"The SEC answered 404 for {url}")
        return self.pages[url]


def test_a_ticker_is_resolved_and_only_annual_filings_are_listed():
    get = FakeSec()
    assert sec.find_company("cvx", get) == (93410, "CHEVRON CORP")
    filings = sec.annual_filings(93410, get)
    # The amendment, the quarterly report and the 8-K are left out.
    assert [(f.form, f.year, f.filed) for f in filings] == [
        ("10-K", 2025, "2026-02-20"),
        ("10-K", 2024, "2025-02-21"),
    ]
    assert filings[0].url == URL_2025
    with pytest.raises(sec.SecError, match="no company with the ticker NOPE"):
        sec.find_company("nope", get)


def test_a_year_without_a_filing_names_the_years_there_are():
    filings = sec.annual_filings(93410, FakeSec())
    assert sec.pick(filings, 2024, "CVX").period_end == "2024-12-31"
    with pytest.raises(sec.SecError, match="No annual filing of CVX for 2019. Years available: "):
        sec.pick(filings, 2019, "CVX")


def test_a_refusal_or_a_non_html_answer_is_not_saved_as_a_filing():
    filing = sec.Filing("10-K", 2025, "2025-12-31", "2026-02-20", URL_2025)
    refused = FakeSec(
        {URL_2025: b"<html>Your Request Originated from an Undeclared Automated Tool"}
    )
    with pytest.raises(sec.SecError, match="refused the request"):
        sec.download(filing, refused)
    with pytest.raises(sec.SecError, match="is not an HTML document"):
        sec.download(filing, FakeSec({URL_2025: b"%PDF-1.7 ..."}))


def test_nothing_is_sent_without_a_contact():
    assert sec.contact_from({"DISCLOSURE_DIFF_SEC_CONTACT": " me@example.org "}) == "me@example.org"
    with pytest.raises(
        sec.SecError, match="Set the environment variable DISCLOSURE_DIFF_SEC_CONTACT"
    ):
        sec.contact_from({})


def test_fetch_stores_filings_by_ticker_and_year_and_notes_their_source(tmp_path, capsys):
    get = FakeSec()
    args = ["--data-dir", str(tmp_path), "fetch", "cvx", "2024", "2025"]
    assert main(args, sec_get=get) == 0
    out = capsys.readouterr().out
    assert "CVX is CHEVRON CORP." in out
    assert "CVX 2025: Form 10-K for the period ending 2025-12-31, filed 2026-02-20" in out

    reports = find_reports(DataDir(tmp_path), company="CVX")
    assert [(r.year, r.is_filing) for r in reports] == [(2024, True), (2025, True)]
    sources = (tmp_path / "reports" / "sources.csv").read_text().splitlines()
    assert sources[0] == "company,year,file,downloaded,source_url,sha256"
    assert sources[2].startswith("CVX,2025,CVX/2025.htm,") and URL_2025 in sources[2]

    # A second run asks the SEC for nothing.
    get.asked.clear()
    assert main(args, sec_get=get) == 0
    assert get.asked == [] and "is already there, skipped" in capsys.readouterr().out


def test_fetch_without_a_contact_or_for_a_missing_year_says_why(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("DISCLOSURE_DIFF_SEC_CONTACT", raising=False)
    assert main(["--data-dir", str(tmp_path), "fetch", "CVX", "2024"]) == 2
    assert "Set the environment variable DISCLOSURE_DIFF_SEC_CONTACT" in capsys.readouterr().err

    assert main(["--data-dir", str(tmp_path), "fetch", "CVX", "2019"], sec_get=FakeSec()) == 2
    assert "No annual filing of CVX for 2019" in capsys.readouterr().err
    assert not (tmp_path / "reports" / "CVX").exists()
