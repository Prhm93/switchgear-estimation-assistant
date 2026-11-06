"""Highlighting finds source texts; it never builds HTML."""

from backend.app.highlight import segments


def test_marks_a_wrapped_clause_and_keeps_the_rest_plain():
    text = "4.1 Form of separation: Form 4a\nto BS EN IEC 61439-2.\n4.2 Degree of protection: IP54"
    segs = segments(text, [(1, "Form of separation: Form 4a", None), (2, "Degree of protection: IP54", None)])
    assert "".join(s.text for s in segs) == text
    assert [s.text for s in segs if s.marked] == ["Form of separation: Form 4a", "Degree of protection: IP54"]


def test_short_numbers_match_whole_words_inside_their_table_row():
    text = "Issue date: 2026-05-12\nQ1 Small power MCB 20 3 10\nQ2 Workshop MCCB 250 4 36"
    segs = segments(text, [(7, "20", "Q1"), (8, "4", "Q2")])
    marked = [(s.text, s.value_ids) for s in segs if s.marked]
    assert marked == [("20", [7]), ("4", [8])]
    assert "".join(s.text for s in segs) == text


def test_overlapping_sources_share_one_span():
    segs = segments("ACB 1250A 4P 50kA", [(1, "ACB 1250A 4P 50kA", None), (2, "ACB 1250A 4P 50kA", None)])
    assert [(s.text, s.value_ids) for s in segs] == [("ACB 1250A 4P 50kA", [1, 2])]


def test_html_in_documents_stays_plain_text_in_segments():
    text = "<script>alert(1)</script> Rated frequency: 50 Hz"
    segs = segments(text, [(1, "Rated frequency: 50 Hz", None)])
    assert segs[0].text == "<script>alert(1)</script> " and not segs[0].marked
