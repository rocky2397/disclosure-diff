import csv
import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
_PAGE_PREFIX = re.compile(r"^Page \d+: ")


@pytest.fixture(scope="session")
def old_false_positives() -> list[str]:
    """Passages the old pipeline marked as relevant to protectionism. None of them is."""
    with (FIXTURES / "old_false_positives.csv").open(encoding="utf-8", newline="") as handle:
        return [_PAGE_PREFIX.sub("", row["content"]) for row in csv.DictReader(handle)]


def _draw_lines(canvas, x, y, lines, *, size=8.5, leading=13):
    canvas.setFont("Helvetica", size)
    for line in lines:
        canvas.drawString(x, y, line)
        y -= leading
    return y


def _draw_report(path, *, bookmarks=True, allow_copy=True):
    """A three-page landscape report laid out like a real one: running header, two
    columns, paragraphs separated by a blank line, a small-print table, bookmarks."""
    from reportlab.pdfgen import canvas as reportlab_canvas

    encrypt = None
    if not allow_copy:
        from reportlab.lib.pdfencrypt import StandardEncryption

        # Opens without a password, but copying and extracting content is switched off.
        encrypt = StandardEncryption("", ownerPassword="owner", canCopy=0, strength=128)
    canvas = reportlab_canvas.Canvas(str(path), pagesize=(842, 595), encrypt=encrypt)

    def start_page(number, *titles):
        _draw_lines(canvas, 160, 550, ["ACME Annual Report 2025 running header"], size=7)
        _draw_lines(canvas, 808, 545, [str(number)], size=9.6)
        for title in titles if bookmarks else ():
            # A leading ">" marks one level of nesting under the bookmark before it.
            level = len(title) - len(title.lstrip(">"))
            title = title.lstrip(">")
            key = f"s{number}-{title}"
            canvas.bookmarkPage(key)
            canvas.addOutlineEntry(title, key, level=level)

    start_page(1, "1 To our investors")
    y = _draw_lines(
        canvas,
        62,
        470,
        [
            "The past year was eventful and also very successful for the company.",
            "We continued to invest in the expansion of our portfolio and delivered",
            "on all of our financial targets despite a volatile environment.",
        ],
    )
    _draw_lines(
        canvas,
        62,
        y - 13,
        [
            "Our shareholders benefit from this through a higher dividend, which",
            "the Board proposes to raise again for the coming financial year.",
        ],
    )
    _draw_lines(
        canvas,
        442,
        470,
        [
            "In the right-hand column we describe our strategy: growth in wind and",
            "solar power, flexible generation and a strong trading business.",
        ],
    )
    canvas.showPage()

    start_page(2, "2 Combined management report", ">2.1 Risks and opportunities")
    _draw_lines(canvas, 62, 470, ["Main risks"])
    _draw_lines(
        canvas,
        62,
        444,
        [
            "New tariffs on imported components could make our projects more expen-",
            "sive, and further trade barriers may delay deliveries from our suppliers",
            "in Asia by several months.",
        ],
    )
    _draw_lines(
        canvas,
        442,
        470,
        ["Risk class 2025 2024", "Market risks 8,000 1,500", "Legal risks 600 300"],
        size=7,
        leading=15,
    )
    canvas.showPage()

    # The notes carry no chapter number, as in E.ON's reports.
    start_page(3, "3 Consolidated financial statements", ">Notes", ">>(1) Accounting policies")
    _draw_lines(
        canvas,
        62,
        470,
        [
            "Trade accounts receivable are measured at amortised cost, and the",
            "expected credit loss is determined by applying the simplified approach.",
        ],
    )
    canvas.showPage()
    canvas.save()
    return path


@pytest.fixture(scope="session")
def report_pdf(tmp_path_factory) -> Path:
    return _draw_report(tmp_path_factory.mktemp("pdf") / "report.pdf")


@pytest.fixture(scope="session")
def report_pdf_without_bookmarks(tmp_path_factory) -> Path:
    return _draw_report(tmp_path_factory.mktemp("pdf") / "plain.pdf", bookmarks=False)


@pytest.fixture(scope="session")
def restricted_report_pdf(tmp_path_factory) -> Path:
    return _draw_report(tmp_path_factory.mktemp("pdf") / "restricted.pdf", allow_copy=False)


def _render(path, *, dpi):
    """The pages of a PDF as pictures."""
    import pypdfium2

    document = pypdfium2.PdfDocument(str(path))
    try:
        return [page.render(scale=dpi / 72).to_pil().convert("RGB") for page in document]
    finally:
        document.close()


@pytest.fixture(scope="session")
def scanned_report_pdf(tmp_path_factory, report_pdf) -> Path:
    """The sample report as a scanner would deliver it: one picture per page, no text."""
    images = _render(report_pdf, dpi=200)
    path = tmp_path_factory.mktemp("pdf") / "scanned.pdf"
    images[0].save(path, "PDF", save_all=True, append_images=images[1:], resolution=200)
    return path


@pytest.fixture(scope="session")
def mixed_page_pdf(tmp_path_factory) -> Path:
    """One page with ordinary text on the left and a picture of a paragraph on the right."""
    from reportlab.pdfgen import canvas as reportlab_canvas

    folder = tmp_path_factory.mktemp("pdf")
    snippet = folder / "snippet.pdf"
    canvas = reportlab_canvas.Canvas(str(snippet), pagesize=(380, 80))
    _draw_lines(
        canvas,
        10,
        60,
        [
            "This paragraph exists only as a picture: export controls on turbine",
            "components delayed two of our projects in Asia by several months,",
            "and further sanctions could interrupt deliveries altogether.",
        ],
    )
    canvas.save()
    picture = folder / "snippet.png"
    _render(snippet, dpi=300)[0].save(picture)

    path = folder / "mixed.pdf"
    canvas = reportlab_canvas.Canvas(str(path), pagesize=(842, 595))
    _draw_lines(
        canvas,
        62,
        470,
        [
            "This paragraph is ordinary text in the file. New tariffs on imported",
            "components could make our projects more expensive, and we are",
            "sourcing more of them from local suppliers.",
        ],
    )
    canvas.drawImage(str(picture), 442, 400, width=380, height=80)
    canvas.save()
    return path


@pytest.fixture(scope="session")
def tight_report_pdf(tmp_path_factory) -> Path:
    """A page set like Chevron's reports: tight lines, and paragraphs only a little further
    apart, so the layout analysis sees one block."""
    from reportlab.pdfgen import canvas as reportlab_canvas

    path = tmp_path_factory.mktemp("pdf") / "tight.pdf"
    canvas = reportlab_canvas.Canvas(str(path), pagesize=(612, 792))
    first = [
        "Trends in the costs of goods and services vary by region and by the kind",
        "of work being done, and the company continues to manage them through",
        "standardization of its designs and optimization of project scope.",
    ]
    second = [
        "In February the government announced the imposition of tariffs on a wide",
        "range of imported goods, and the effect of these measures on our results",
        "of operations and financial condition remains uncertain at this time.",
    ]
    y = _draw_lines(canvas, 52, 700, first, size=10.2, leading=12.8)
    _draw_lines(canvas, 52, y - 5.1, second, size=10.2, leading=12.8)
    canvas.save()
    return path
