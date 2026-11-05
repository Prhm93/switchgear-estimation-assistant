"""Box maths must match image maths: a warped box equals the box of the warped pixels."""

import numpy as np
import pytest
from PIL import Image

from data_generator import geometry as g


def test_mm_to_px_flips_y_and_scales():
    # 25.4 mm is one inch; at 100 dpi that is 100 px. y is measured from the top.
    assert g.mm_to_px(25.4, 297.0, 297.0, 100) == (pytest.approx(100.0), pytest.approx(0.0))
    assert g.mm_to_px(0.0, 0.0, 297.0, 100)[1] == pytest.approx(297 / 25.4 * 100)


def test_mm_box_to_px_orders_corners():
    x0, y0, x1, y1 = g.mm_box_to_px([10, 20, 30, 50], 297, 150)
    assert x0 < x1 and y0 < y1


def test_homography_maps_the_four_points():
    src = [[0, 0], [100, 0], [100, 80], [0, 80]]
    dst = [[5, 3], [97, 8], [102, 85], [-2, 77]]
    h = g.homography_from_points(src, dst)
    assert np.allclose(g.apply(h, src), dst, atol=1e-9)


def test_rotation_keeps_the_centre():
    h = g.rotation_about(50, 40, 7.5)
    assert np.allclose(g.apply(h, [[50, 40]]), [[50, 40]])


def _warp_mask(box, size, h):
    """Paint ``box`` white on black, warp it with Pillow, return the box of the result."""
    img = Image.new("L", size, 0)
    x0, y0, x1, y1 = box
    img.paste(255, (int(x0), int(y0), int(x1), int(y1)))
    out = img.transform(size, Image.Transform.PERSPECTIVE, g.pil_perspective_coeffs(h),
                        resample=Image.Resampling.BILINEAR)
    ys, xs = np.nonzero(np.asarray(out) > 127)
    return [xs.min(), ys.min(), xs.max() + 1, ys.max() + 1]


@pytest.mark.parametrize(
    "h",
    [
        g.rotation_about(400, 300, 1.8, dx=6, dy=-4),
        g.rotation_about(400, 300, -2.5),
        g.homography_from_points(
            [[0, 0], [800, 0], [800, 600], [0, 600]],
            [[40, 25], [770, 60], [740, 590], [15, 560]],
        ),
    ],
    ids=["rotate+shift", "rotate", "perspective"],
)
def test_transformed_box_matches_warped_pixels(h):
    size = (800, 600)
    for box in ([100, 120, 160, 200], [500, 300, 620, 340], [300, 450, 330, 560]):
        expected = g.transform_box(h, box)
        got = _warp_mask(box, size, h)
        # A box warps into a quadrilateral, so its axis-aligned hull is the right
        # comparison; the two agree to within resampling (about one pixel).
        assert np.allclose(got, expected, atol=1.5), (box, got, expected)


def test_clip_and_iou():
    assert g.clip_box([-5, -1, 50, 900], 100, 800) == [0.0, 0.0, 50.0, 800.0]
    assert g.iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert g.iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0
