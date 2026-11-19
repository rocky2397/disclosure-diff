"""The reports in the data folder.

A report is stored as ``reports/<COMPANY>/<year>.pdf``, or as ``<year>.htm`` for a filing
with the SEC. The year is the reporting year and is the whole file name, because original
file names are ambiguous: RWE publishes its 2024 report as
``2025-03-20-rwe-annual-report-2024.pdf``.
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from document_impact_analyzer.settings import DataDir, is_sidecar

_YEAR_FILE = re.compile(r"^((?:19|20)\d\d)\.(?:pdf|html?)$", re.IGNORECASE)
# A report is a PDF, or the HTML of a filing with the SEC.
REPORT_SUFFIXES = (".pdf", ".htm", ".html")


@dataclass(frozen=True)
class ReportFile:
    company: str
    year: int
    path: Path

    @property
    def is_filing(self) -> bool:
        """An HTML filing with the SEC, as opposed to a PDF report."""
        return self.path.suffix.lower() != ".pdf"


def find_reports(data: DataDir, company: str | None = None) -> list[ReportFile]:
    """Reports in the data folder, sorted by company and year.

    Raises ``ValueError`` for a report whose name is not a year, so that a misnamed report
    is noticed instead of silently left out, and for two reports of the same year.
    """
    reports = []
    if not data.reports.is_dir():
        return reports
    for folder in sorted(p for p in data.reports.iterdir() if p.is_dir()):
        if company and folder.name != company:
            continue
        by_year: dict[int, Path] = {}
        for path in sorted(folder.iterdir()):
            if is_sidecar(path) or path.suffix.lower() not in REPORT_SUFFIXES:
                continue
            found = _YEAR_FILE.match(path.name)
            if not found:
                raise ValueError(
                    f"{path}: name the file after its reporting year, for example 2024.pdf"
                )
            year = int(found.group(1))
            if year in by_year:
                raise ValueError(
                    f"{folder.name} has two reports for {year}: {by_year[year].name} and "
                    f"{path.name}. Keep one, or put the other under another company name."
                )
            by_year[year] = path
            reports.append(ReportFile(folder.name, year, path))
    return reports


def extracted_path(data: DataDir, company: str, year: int) -> Path:
    return data.extracted / f"{company}_{year}.jsonl"


def record_source(data: DataDir, report: ReportFile, url: str, content: bytes) -> None:
    """Note in ``reports/sources.csv`` where a downloaded report came from, with a checksum."""
    path = data.reports / "sources.csv"
    new = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        if new:
            writer.writerow(["company", "year", "file", "downloaded", "source_url", "sha256"])
        file = f"{report.company}/{report.path.name}"
        checksum = hashlib.sha256(content).hexdigest()
        writer.writerow(
            [report.company, report.year, file, date.today().isoformat(), url, checksum]
        )
