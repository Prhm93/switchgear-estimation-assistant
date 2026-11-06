"""Combined mode: agreement is marked; disagreement keeps both values for Stage 6."""

from __future__ import annotations

from backend.app.llm.combine import combine
from backend.app.schemas import Agreement, Confidence, DocumentKind, ExtractedValue, Method, SourceRef


def value(field: str, v, unit: str | None, method: Method, page: int = 3, text: str = "x") -> ExtractedValue:
    return ExtractedValue(field=field, value=v, unit=unit, method=method, confidence=Confidence.HIGH,
                          source=SourceRef(document=DocumentKind.SPECIFICATION, file="specification.pdf", page=page,
                                           source_text=text))


def test_agree_keeps_one_value_and_marks_it() -> None:
    rules = [value("way.Q1.rating", 250, "A", Method.RULES)]
    llm = [value("way.Q1.rating", 250.0, "A", Method.LLM, text="Q1 Chiller 250A")]
    out = combine(rules, llm)
    assert len(out) == 1
    assert out[0].method == Method.RULES and out[0].agreement == Agreement.AGREE
    assert "Q1 Chiller 250A" in out[0].derivation


def test_disagree_keeps_both() -> None:
    rules = [value("way.Q1.rating", 250, "A", Method.RULES)]
    llm = [value("way.Q1.rating", 200, "A", Method.LLM)]
    out = combine(rules, llm)
    assert sorted((v.method.value, v.value, v.agreement.value) for v in out) == [
        ("llm", 200, "disagree"), ("rules", 250, "disagree")]


def test_one_method_only() -> None:
    out = combine([value("system.voltage", 400, "V", Method.RULES)],
                  [value("system.frequency", 50, "Hz", Method.LLM)])
    assert {(v.field, v.agreement) for v in out} == {("system.voltage", Agreement.RULES_ONLY),
                                                      ("system.frequency", Agreement.LLM_ONLY)}


def test_pages_are_compared_separately() -> None:
    out = combine([value("ways.count", 8, None, Method.RULES, page=2)], [value("ways.count", 8, None, Method.LLM, page=5)])
    assert {(v.source.page, v.agreement) for v in out} == {(2, Agreement.RULES_ONLY), (5, Agreement.LLM_ONLY)}


def test_inputs_are_not_changed() -> None:
    rules = [value("system.voltage", 400, "V", Method.RULES)]
    combine(rules, [value("system.voltage", 400, "V", Method.LLM)])
    assert rules[0].agreement is None
