"""Tests for the number check. No model needed."""

import pytest

from estimation_assistant.checks import find_numbers, unsupported_numbers
from estimation_assistant.schemas import AgentResult, ToolStep

PRICE_STEP = ToolStep(name="lookup_price", arguments={"part_name": "busbar"}, result="95.0")
TOTAL_STEP = ToolStep(
    name="line_total", arguments={"unit_price": 95, "quantity": 3}, result="285"
)


def result(answer: str, *steps: ToolStep) -> AgentResult:
    return AgentResult(answer=answer, steps=list(steps))


@pytest.mark.parametrize(
    "text, numbers",
    [
        ("3 busbars at 95.0", [3.0, 95.0]),
        ("The total is 2,850.00.", [2850.0]),
        ("1,234,567", [1234567.0]),
        ("£95", [95.0]),
        ("Source D2 and part X10", []),
        ("no numbers here", []),
    ],
)
def test_find_numbers(text, numbers):
    assert find_numbers(text) == numbers


@pytest.mark.parametrize(
    "text, numbers",
    [
        ("three busbars", []),
        ("-5", [5.0]),
        (".5", [5.0]),
        ("3rd", [3.0]),
        ("2,85", [2.0, 85.0]),
    ],
)
def test_find_numbers_known_limits(text, numbers):
    # These record the limits listed in the README, not the wanted behaviour
    assert find_numbers(text) == numbers


def test_number_from_a_tool_result_is_supported():
    assert unsupported_numbers("Price of a busbar?", result("It is 95.0.", PRICE_STEP)) == []


def test_number_from_a_tool_input_is_supported():
    assert unsupported_numbers("Total?", result("3 at 95 is 285.", TOTAL_STEP)) == []


def test_number_from_the_question_is_supported():
    assert unsupported_numbers("Is it 42?", result("Yes, 42.")) == []


def test_formatting_of_a_number_does_not_matter():
    assert unsupported_numbers("Total?", result("The total is 285.00.", TOTAL_STEP)) == []


def test_number_with_no_evidence_is_flagged():
    assert unsupported_numbers("Price?", result("It is 120.", PRICE_STEP)) == [120.0]


def test_only_the_unbacked_numbers_are_flagged():
    answer = "95.0 each, so 300 for 3."
    assert unsupported_numbers("3 busbars?", result(answer, PRICE_STEP)) == [300.0]


def test_answer_with_no_numbers_has_nothing_to_flag():
    assert unsupported_numbers("Which part?", result("A busbar.", PRICE_STEP)) == []


def test_note_text_counts_as_evidence():
    note = ToolStep(
        name="search_notes",
        arguments={"question": "rating"},
        result="Source D9 (score 0.8): The rating is 630 amps.",
    )
    assert unsupported_numbers("Rating?", result("It is 630 amps.", note)) == []


def test_a_number_used_wrongly_is_not_caught():
    # The check proves a number exists in the evidence, not that it is right
    assert unsupported_numbers("Total?", result("The total is 95.", TOTAL_STEP)) == []
