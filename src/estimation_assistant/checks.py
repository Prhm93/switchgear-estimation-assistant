"""Checks that an agent answer is backed by its tool results."""

import re
from .schemas import AgentResult

# A number: digits with an optional thousands separator and decimals.
# The lookbehind skips digits that belong to a word, such as the 2 in "D2".
NUMBER = re.compile(
    r"(?<![A-Za-z0-9])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
)


def find_numbers(text: str) -> list[float]:
    """Return every number in the text as a float."""
    numbers = []
    for match in NUMBER.findall(text):
        # Remove thousands separators so "2,850.00" becomes 2850.0
        numbers.append(float(match.replace(",", "")))
    return numbers

def unsupported_numbers(question: str, result: AgentResult) -> list[float]:
    """Return the numbers in the answer that appear nowhere in the question or the run log."""
    # Collect every number the answer is allowed to use, rounded to 2 decimals
    allowed = set()
    for number in find_numbers(question):
        allowed.add(round(number, 2))
    for step in result.steps:
        for number in find_numbers(step.result) + find_numbers(str(step.arguments)):
            allowed.add(round(number, 2))

    # Anything in the answer outside that set was not backed by evidence
    return [n for n in find_numbers(result.answer) if round(n, 2) not in allowed]