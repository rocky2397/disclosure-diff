import pytest

from disclosure_diff.library import ReportFile, extracted_path, find_reports
from disclosure_diff.settings import DataDir


@pytest.fixture
def data(tmp_path):
    for name in ("RWE/2025.pdf", "RWE/2024.pdf", "RWE/._2024.pdf", "RWE/notes.txt", "BP/2023.PDF"):
        path = tmp_path / "reports" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    return DataDir(tmp_path)


def test_reports_are_found_by_company_and_year(data):
    assert find_reports(data) == [
        ReportFile("BP", 2023, data.reports / "BP" / "2023.PDF"),
        ReportFile("RWE", 2024, data.reports / "RWE" / "2024.pdf"),
        ReportFile("RWE", 2025, data.reports / "RWE" / "2025.pdf"),
    ]
    assert [r.year for r in find_reports(data, company="RWE")] == [2024, 2025]
    assert find_reports(data, company="EON") == []


def test_misnamed_report_is_an_error(data):
    (data.reports / "RWE" / "2025-03-20-rwe-annual-report-2024.pdf").write_bytes(b"")
    with pytest.raises(ValueError, match="name the file after its reporting year"):
        find_reports(data)


def test_missing_reports_folder(tmp_path):
    assert find_reports(DataDir(tmp_path)) == []


def test_extracted_path(data):
    assert extracted_path(data, "RWE", 2024) == data.extracted / "RWE_2024.jsonl"


def test_a_filing_is_a_report_too_and_a_year_can_have_only_one(data):
    (data.reports / "CVX").mkdir()
    (data.reports / "CVX" / "2024.htm").write_bytes(b"")
    (report,) = find_reports(data, company="CVX")
    assert (report.year, report.is_filing) == (2024, True)
    assert not find_reports(data, company="RWE")[0].is_filing

    (data.reports / "CVX" / "2024.pdf").write_bytes(b"")
    with pytest.raises(ValueError, match="CVX has two reports for 2024: 2024.htm and 2024.pdf"):
        find_reports(data)
