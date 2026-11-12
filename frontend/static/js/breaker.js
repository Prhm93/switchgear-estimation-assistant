/*
 * The breaker drawing: explode, leader lines that follow their parts, and hover linking.
 *
 * Every part group carries its projected explode vector (--dx, --dy, in drawing units); CSS moves it by
 * that vector times --explode. A leader line ends on its part's anchor point, so when the part moves
 * the end of the leader moves with it: its last point is anchor + explode * (dx, dy).
 * Hovering or focusing a part or a label highlights both (matched by data-part).
 */
(function () {
  "use strict";

  function setExplode(svg, value) {
    var v = Math.min(1, Math.max(0, Number(value) || 0));
    svg.style.setProperty("--explode", v.toFixed(3));
    svg.querySelectorAll(".bk-leader").forEach(function (leader) {
      var d = leader.dataset;
      var x = Number(d.ax) + v * Number(d.dx);
      var y = Number(d.ay) + v * Number(d.dy);
      leader.setAttribute("d", "M" + d.x + " " + d.y + "H" + d.elbow + "L" + x.toFixed(1) + " " + y.toFixed(1));
    });
  }

  function link(svg) {
    function mark(part, on) {
      svg.querySelectorAll('[data-part="' + part + '"]').forEach(function (el) {
        el.classList.toggle("is-active", on);
      });
    }
    svg.querySelectorAll(".bk-part, .bk-label").forEach(function (el) {
      var part = el.dataset.part;
      el.addEventListener("mouseenter", function () { mark(part, true); });
      el.addEventListener("mouseleave", function () { mark(part, false); });
      el.addEventListener("focusin", function () { mark(part, true); });
      el.addEventListener("focusout", function () { mark(part, false); });
    });
  }

  function trip(svg) {
    svg.classList.remove("is-tripped");
    void svg.getBoundingClientRect();  // restart the one-time animation
    svg.classList.add("is-tripped");
  }

  window.SeaBreaker = { setExplode: setExplode, trip: trip };

  document.querySelectorAll("[data-breaker]").forEach(function (frame) {
    var svg = frame.querySelector("svg.breaker");
    if (!svg) return;
    link(svg);
    var slider = document.querySelector("[data-breaker-explode]");
    if (slider) {
      slider.addEventListener("input", function () { setExplode(svg, slider.value); });
    }
    var live = document.querySelector("[data-breaker-live]");
    if (live) {
      live.addEventListener("change", function () { svg.classList.toggle("is-live", live.checked); });
    }
    var button = document.querySelector("[data-breaker-trip]");
    if (button) {
      button.addEventListener("click", function () { trip(svg); });
    }
  });
})();
