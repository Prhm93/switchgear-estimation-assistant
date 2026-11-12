"""The proof viewer's selection script (frontend/static/js/proof.js), run in Node against a small fake page.

The fake page has two boxes on the drawing, their two value cards with "Show on the drawing", and the text panel's
marks. Clicking a box marks its card; clicking a card's link marks and pulses its box and its text line; Enter on a
focused box selects it; only one box and one card are ever active. No browser and no new library: the test skips
when Node is not installed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "frontend" / "static" / "js" / "proof.js"
NODE = shutil.which("node")

FAKE_PAGE = r"""
function El(id, attrs, parent) {
  var self = this;
  this.id = id; this.attrs = attrs || {}; this.parent = parent || null; this.classes = new Set(); this.scrolled = 0;
  this.classList = { add: function (c) { self.classes.add(c); }, remove: function (c) { self.classes.delete(c); },
                     contains: function (c) { return self.classes.has(c); } };
}
El.prototype.getAttribute = function (n) { return n in this.attrs ? this.attrs[n] : null; };
El.prototype.setAttribute = function (n, v) { this.attrs[n] = String(v); };
El.prototype.removeAttribute = function (n) { delete this.attrs[n]; };
El.prototype.closest = function (sel) {
  var m = sel.match(/^\[([\w-]+)\]$/);
  for (var e = this; e; e = e.parent) { if (m && m[1] in e.attrs) return e; }
  return null;
};
El.prototype.scrollIntoView = function () { this.scrolled++; };
El.prototype.getBoundingClientRect = function () { return { width: 0, height: 0 }; };

var all = [], handlers = {};
function add(id, attrs, parent) { var e = new El(id, attrs, parent); all.push(e); return e; }
function box(n, tone) {
  var a = add("box-" + n, { "data-box": String(n), "data-tone": tone, "data-read": "Value " + n,
                            "data-x": "10", "data-y": "10", "data-w": "40", "data-h": "20", "data-pad": "4" });
  add(null, {}, a);  // the <rect> inside the box: clicks land on it
  return a;
}
box(7, "picture"); box(8, "symbol");
[7, 8].forEach(function (n) { var card = add("v-" + n, {}); add(null, { "data-show": String(n) }, card); });
add("src-7", { "data-values": "7" }); add("src-8", { "data-values": "3 8" });

global.window = global;
global.document = {
  getElementById: function (id) { return all.find(function (e) { return e.id === id; }) || null; },
  querySelector: function () { return null; },
  querySelectorAll: function (sel) {
    var parts = sel.split(",").map(function (s) { return s.trim(); });
    return all.filter(function (e) {
      return parts.some(function (p) {
        if (p[0] === ".") return e.classes.has(p.slice(1));
        var m = p.match(/^\[([\w-]+)\]$/); return m && m[1] in e.attrs;
      });
    });
  },
  addEventListener: function (type, fn) { (handlers[type] = handlers[type] || []).push(fn); }
};
require(process.argv[process.argv.length - 1]);  // the script under test

function fire(type, target, key) {
  var ev = { type: type, target: target, key: key, prevented: false, preventDefault: function () { this.prevented = true; } };
  (handlers[type] || []).forEach(function (fn) { fn(ev); });
  return ev;
}
function rect(n) { return all.find(function (e) { return e.parent && e.parent.id === "box-" + n; }); }
function show(n) { return all.find(function (e) { return e.attrs["data-show"] === String(n); }); }
function state() {
  return {
    active: all.filter(function (e) { return e.classes.has("is-active"); }).map(function (e) { return e.id; }).sort(),
    pulse: all.filter(function (e) { return e.classes.has("is-pulse"); }).map(function (e) { return e.id; }),
    scrolled: all.filter(function (e) { return e.scrolled; }).map(function (e) { return e.id; })
  };
}
function reset() { all.forEach(function (e) { e.scrolled = 0; }); }
"""


def run(steps: str) -> dict:
    """Run the fake page, then ``steps`` (JavaScript that sets ``out``), and return ``out``."""
    code = FAKE_PAGE + "\nvar out = {};\n" + steps + "\nconsole.log(JSON.stringify(out));\n"
    done = subprocess.run([NODE, "-e", code, "--", str(SCRIPT)], capture_output=True, text=True, timeout=30,
                          check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


pytestmark = pytest.mark.skipif(NODE is None, reason="Node is not installed; the proof viewer script is not run")


def test_click_on_a_box_marks_its_card_and_scrolls_it_into_view() -> None:
    out = run("""
        var ev = fire("click", rect(7));
        out.prevented = ev.prevented; out.s = state();
    """)
    assert out["prevented"] is True  # no jump to #v-7: the card is scrolled into view instead
    assert out["s"]["active"] == ["box-7", "src-7", "v-7"]
    assert "v-7" in out["s"]["scrolled"]


def test_click_on_show_on_the_drawing_marks_and_pulses_its_box_and_its_text_line() -> None:
    out = run("""
        fire("click", show(8)); out.s = state();
    """)
    assert out["s"]["active"] == ["box-8", "src-8", "v-8"]  # src-8 holds values 3 and 8
    assert out["s"]["pulse"] == ["box-8"]
    assert "box-8" in out["s"]["scrolled"]


def test_only_one_box_and_one_card_are_active_at_a_time() -> None:
    out = run("""
        fire("click", rect(7)); fire("click", show(8)); out.a = state();
        fire("click", rect(7)); out.b = state();
    """)
    assert out["a"]["active"] == ["box-8", "src-8", "v-8"]
    assert out["b"]["active"] == ["box-7", "src-7", "v-7"] and out["b"]["pulse"] == []


def test_enter_on_a_focused_box_selects_it() -> None:
    out = run("""
        var ev = fire("keydown", document.getElementById("box-8"), "Enter"); out.prevented = ev.prevented;
        out.s = state(); fire("keydown", document.getElementById("box-7"), "Tab"); out.t = state();
    """)
    assert out["prevented"] is True and out["s"]["active"] == ["box-8", "src-8", "v-8"]
    assert out["t"]["active"] == ["box-8", "src-8", "v-8"]  # other keys change nothing


def test_the_enlarged_crop_is_three_times_the_box_and_turns_vertical_text_upright() -> None:
    out = run("""
        out.flat = SheetProof.zoomView({x: 100, y: 50, w: 80, h: 20, pad: 5}, 0.5);
        out.tall = SheetProof.zoomView({x: 100, y: 50, w: 20, h: 80, pad: 5}, 0.5);
    """)
    flat, tall = out["flat"], out["tall"]
    assert flat["viewBox"] == "0 0 90 30" and flat["turned"] is False  # the box and one padding around it
    assert flat["width"] == round(90 * 0.5 * 3)  # about three times its size on the drawing
    assert flat["transform"] == "translate(-95 -45)"
    assert tall["turned"] is True and tall["viewBox"] == "0 0 90 30"  # turned a quarter: now wide, not tall
    assert tall["transform"] == "translate(90 0) rotate(90) translate(-95 -45)"
    assert tall["width"] == round(90 * 0.5 * 3)
