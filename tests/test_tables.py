import pytest

from disclosure_diff.tables import figure_share, looks_like_table

PROSE = [
    "New tariffs on steel imports raised our procurement costs by $120 million in 2023, "
    "and we expect a further increase of around 5% next year if the measures stay in place.",
    "In 2022 and 2023 the group reviewed its exposure to export controls in all regions.",
    "A US holder who sells or otherwise disposes of ordinary shares will recognize a capital "
    "gain or loss for US federal income tax purposes.",
]

TABLES = [
    "Trade receivables 22,307 17 12,926 19 Other receivables 2,874 472 2,628 637",
    "Interest and debt expense $ 516 $ 712 $ 697 Research and development expenses "
    "$ 268 $ 268 $ 435",
    "Balance at 1 Jan 2022 3 2 11 16 Level transfer – 2 – 2 Currency adjustments 1 1",
]


@pytest.mark.parametrize("text", PROSE)
def test_prose_is_kept(text):
    assert not looks_like_table(text)


@pytest.mark.parametrize("text", TABLES)
def test_table_rows_are_detected(text):
    assert looks_like_table(text)


def test_short_text_is_never_a_table():
    assert not looks_like_table("2023 2022")


def test_figure_share_counts_amounts_and_empty_cells():
    assert figure_share("Total 1,401 – (147) 25%") == pytest.approx(4 / 5)
    assert figure_share("") == 0.0


def test_old_false_positives_that_are_tables(old_false_positives):
    # Rows 0-3 and 8 of the fixture are financial statement tables; the rest are prose
    # from the notes, which the section filter and topic retrieval have to reject.
    flagged = {i for i, text in enumerate(old_false_positives) if looks_like_table(text)}
    assert flagged == {0, 1, 2, 3, 8}
