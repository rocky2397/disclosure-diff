"""Fetch a company's annual filing from the SEC's EDGAR system.

EDGAR is free and needs no key, but it asks every automated tool to say who is asking: a
contact address in the User-Agent header. This module takes that address from the
environment variable ``DIA_SEC_CONTACT`` and sends nothing without it.

An annual filing is a Form 10-K, or a 20-F or 40-F for a foreign company. Its year is the
year in which the reported period ends, which is how companies name their fiscal years:
a period ending in January 2025 is fiscal 2025.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass

CONTACT_ENV = "DIA_SEC_CONTACT"
ANNUAL_FORMS = ("10-K", "20-F", "40-F")
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
DOCUMENT_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{document}"
# The SEC allows ten requests a second. A short pause keeps well below that.
_PAUSE_SECONDS = 0.2

Get = Callable[[str], bytes]


class SecError(RuntimeError):
    """A filing could not be found or fetched."""


@dataclass(frozen=True)
class Filing:
    form: str
    # The year in which the reported period ends.
    year: int
    period_end: str
    filed: str
    url: str


def contact_from(environ: Mapping[str, str] | None = None) -> str:
    contact = (os.environ if environ is None else environ).get(CONTACT_ENV, "").strip()
    if not contact:
        raise SecError(
            "The SEC asks automated tools to name a contact. Set the environment variable "
            f"{CONTACT_ENV} to your e-mail address and run the command again."
        )
    return contact


def http_get(contact: str) -> Get:
    """A function that fetches a URL from the SEC, naming ``contact`` as the SEC asks."""
    headers = {"User-Agent": f"disclosure-diff {contact}"}

    def get(url: str) -> bytes:
        time.sleep(_PAUSE_SECONDS)
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            raise SecError(f"The SEC answered {error.code} for {url}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise SecError(f"Could not reach the SEC: {error}") from error

    return get


def _json(get: Get, url: str) -> dict:
    try:
        return json.loads(get(url))
    except ValueError as error:
        raise SecError(f"The SEC did not return data for {url}") from error


def find_company(ticker: str, get: Get) -> tuple[int, str]:
    """The SEC's number (CIK) and name for a ticker symbol."""
    wanted = ticker.strip().upper()
    for entry in _json(get, TICKERS_URL).values():
        if str(entry.get("ticker", "")).upper() == wanted:
            return int(entry["cik_str"]), str(entry.get("title", wanted))
    raise SecError(f"The SEC lists no company with the ticker {wanted}.")


def annual_filings(cik: int, get: Get) -> list[Filing]:
    """The company's recent annual filings, newest first. Amendments are left out."""
    recent = _json(get, SUBMISSIONS_URL.format(cik=cik)).get("filings", {}).get("recent", {})
    columns = ("form", "reportDate", "filingDate", "accessionNumber", "primaryDocument")
    rows = zip(*(recent.get(column, []) for column in columns), strict=False)
    filings = []
    for form, period_end, filed, accession, document in rows:
        if form not in ANNUAL_FORMS or not period_end or not document:
            continue
        url = DOCUMENT_URL.format(cik=cik, folder=accession.replace("-", ""), document=document)
        filings.append(Filing(form, int(period_end[:4]), period_end, filed, url))
    return filings


def pick(filings: list[Filing], year: int, ticker: str) -> Filing:
    for filing in filings:
        if filing.year == year:
            return filing
    years = ", ".join(str(y) for y in sorted({filing.year for filing in filings})) or "none"
    raise SecError(f"No annual filing of {ticker} for {year}. Years available: {years}.")


def download(filing: Filing, get: Get) -> bytes:
    """The main document of a filing."""
    content = get(filing.url)
    if b"Undeclared Automated Tool" in content[:5000]:
        raise SecError(f"The SEC refused the request. Check the contact in {CONTACT_ENV}.")
    if b"<html" not in content[:5000].lower() and b"<?xml" not in content[:200].lower():
        raise SecError(f"{filing.url} is not an HTML document.")
    return content
