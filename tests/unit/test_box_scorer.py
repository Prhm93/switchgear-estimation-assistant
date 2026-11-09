"""The box scorer (Stage 4): IoU, and one-to-one matching of predicted boxes to answer-key boxes.

A prediction counts as right when it has the same class as an unmatched
answer-key box and their IoU is at least the threshold (0.5 by default).
Predictions are taken in order of score, highest first; each takes the
unmatched answer box of its class with the largest IoU. Every answer box is
matched at most once.
"""

from __future__ import annotations

import pytest

from backend.app.drawing.boxes import Box, iou, match_boxes, total

A = [0.0, 0.0, 10.0, 10.0]


def test_iou_of_identical_disjoint_and_half_overlapping_boxes() -> None:
    assert iou(A, A) == 1.0
    assert iou(A, [20, 20, 30, 30]) == 0.0
    assert iou(A, [5, 0, 15, 10]) == pytest.approx(50 / 150)
    assert iou(A, [10, 0, 20, 10]) == 0.0  # touching edges share no area


def test_a_right_box_is_a_true_positive_with_its_iou() -> None:
    scores = match_boxes([Box("mccb", [1, 0, 11, 10], 0.9)], [Box("mccb", A)])
    s = scores["mccb"]
    assert (s.tp, s.fp, s.fn) == (1, 0, 0)
    assert s.mean_iou == pytest.approx(90 / 110)
    assert s.precision == s.recall == s.f1 == 1.0


def test_one_answer_box_is_matched_at_most_once() -> None:
    scores = match_boxes([Box("mccb", A, 0.9), Box("mccb", A, 0.8)], [Box("mccb", A)])
    assert (scores["mccb"].tp, scores["mccb"].fp, scores["mccb"].fn) == (1, 1, 0)


def test_the_wrong_class_is_a_false_positive_and_a_miss() -> None:
    scores = match_boxes([Box("mcb", A, 0.9)], [Box("mccb", A)])
    assert (scores["mcb"].tp, scores["mcb"].fp, scores["mcb"].fn) == (0, 1, 0)
    assert (scores["mccb"].tp, scores["mccb"].fp, scores["mccb"].fn) == (0, 0, 1)


def test_overlap_below_the_threshold_does_not_count() -> None:
    low = [7, 0, 17, 10]  # IoU 30/170, about 0.18
    assert match_boxes([Box("ct", low, 0.9)], [Box("ct", A)])["ct"].tp == 0
    assert match_boxes([Box("ct", low, 0.9)], [Box("ct", A)], threshold=0.1)["ct"].tp == 1


def test_the_higher_score_takes_the_match() -> None:
    near, far = [0, 0, 10, 11], [3, 0, 13, 10]
    scores = match_boxes([Box("acb", far, 0.4), Box("acb", near, 0.95)], [Box("acb", A)])
    assert scores["acb"].tp == 1 and scores["acb"].mean_iou == pytest.approx(100 / 110)


def test_each_prediction_takes_the_best_unmatched_box_of_its_class() -> None:
    truth = [Box("mccb", A), Box("mccb", [20, 0, 30, 10])]
    preds = [Box("mccb", [19, 0, 29, 10], 0.9), Box("mccb", [1, 0, 11, 10], 0.8)]
    assert match_boxes(preds, truth)["mccb"].tp == 2


def test_totals_add_up_over_classes_and_empty_inputs_give_no_scores() -> None:
    scores = match_boxes([Box("mccb", A, 0.9), Box("earth", [50, 50, 60, 60], 0.5)],
                         [Box("mccb", A), Box("mcb", [80, 80, 90, 90])])
    t = total(scores)
    assert (t.tp, t.fp, t.fn) == (1, 1, 1)
    assert match_boxes([], []) == {}
    assert total({}).precision is None and total({}).f1 is None
