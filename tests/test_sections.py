import pytest

from disclosure_diff.sections import (
    Section,
    chapter_of,
    clean_title,
    is_narrative,
    section_for_page,
)

# The bookmarks of RWE's 2025 annual report, shortened.
SECTIONS = [
    Section("At a glance", 3),
    Section("Contents", 4),
    Section("1 To our investors", 5),
    Section("1.1 Letter from the CEO", 6),
    Section("1.3 Supervisory Board report", 9),
    Section("2 Combined management report", 20),
    Section("2.3 Business environment", 31),
    Section("2.7 Notes to the financial statements of RWE AG (holding company)", 56),
    Section("2.9 Development of risks and opportunities", 60),
    Section("3 Consolidated financial statements", 165),
    Section("3.1 Income statement", 166),
    Section("3.6 Notes", 174),
    Section("3.8 Boards (part of the Notes)", 320),
    Section("4 Note from the -auditor", 327),
    Section("6 Further information", 342),
    Section("6.2 Imprint", 344),
]


def by_title(start):
    return next(s for s in SECTIONS if s.title.startswith(start))


def test_number_and_name():
    section = by_title("2.9")
    assert section.number == "2.9"
    assert section.name == "Development of risks and opportunities"
    assert by_title("At a glance").number is None


def test_clean_title():
    assert clean_title("2.9  Development of\nrisks ") == "2.9 Development of risks"


@pytest.mark.parametrize(
    ("page", "title"),
    [(1, None), (3, "At a glance"), (30, "2 Combined"), (31, "2.3"), (64, "2.9"), (400, "6.2")],
)
def test_section_for_page(page, title):
    section = section_for_page(SECTIONS, page)
    assert (section.title if section else None) == (by_title(title).title if title else None)


def test_chapter_comes_from_the_numbering():
    assert chapter_of(SECTIONS, by_title("2.9")) == by_title("2 Combined")
    assert chapter_of(SECTIONS, by_title("2 Combined")) is None
    assert chapter_of(SECTIONS, by_title("Contents")) is None


@pytest.mark.parametrize("start", ["1.1", "1.3", "2 Combined", "2.3", "2.9", "1 To our"])
def test_narrative_sections(start):
    assert is_narrative(by_title(start), SECTIONS)


@pytest.mark.parametrize(
    "start", ["Contents", "At a glance", "2.7", "3 Consolidated", "3.1", "3.6", "3.8", "4 ", "6.2"]
)
def test_other_sections(start):
    assert not is_narrative(by_title(start), SECTIONS)


def test_pages_without_a_section_are_searched():
    assert is_narrative(None)


# The bookmarks of E.ON's 2024 report, shortened. They carry no chapter numbers, and the
# notes are numbered in brackets underneath "Notes".
EON = [
    Section("To Our Investors", 14),
    Section("CEO Letter", 19, ("To Our Investors",)),
    Section("Combined Group Management Report", 26),
    Section("Risks and Chances Report", 99, ("Combined Group Management Report",)),
    Section(
        "Composition of Share Capital",
        106,
        ("Combined Group Management Report", "Disclosures Regarding Takeovers"),
    ),
    Section("Consolidated Financial Statements", 132),
    Section("Consolidated Statement of Income", 133, ("Consolidated Financial Statements",)),
    Section("Consolidated Statement of Cash Flows", 137, ("Consolidated Financial Statements",)),
    Section("Notes", 141, ("Consolidated Financial Statements",)),
    Section(
        "(1) Summary of Significant Accounting Policies",
        141,
        ("Consolidated Financial Statements", "Notes"),
    ),
    Section("(34) Segment Reporting", 215, ("Consolidated Financial Statements", "Notes")),
    Section("Declaration of the Board of Management", 255, ("Other Information",)),
    Section("Summary of Financial Highlights", 271, ("Other Information",)),
]


def test_nesting_decides_when_there_are_no_chapter_numbers():
    narrative = [s.title for s in EON if is_narrative(s, EON)]
    assert narrative == [
        "To Our Investors",
        "CEO Letter",
        "Combined Group Management Report",
        "Risks and Chances Report",
    ]
