/*
 * Home page motion, written by hand (no library). Needs breaker.js (window.SeaBreaker).
 *
 * - The top bar height goes into --nav-h, so the story card sticks just under it.
 * - The hero drawing draws itself on load in about 3 s: the parts first, from the frame outwards, then
 *   the leader lines, then the labels. After that the whole hero scene (headline, buttons and drawing) is
 *   pinned (CSS, position: sticky) while the taller hero scrolls by, and the scroll through the pinned part
 *   opens the drawing and closes it again (SeaBreaker.setExplode, 0 to 1 to 0, a half sine of the progress).
 *   At the end of the pin the drawing is closed, the pin releases and the page scrolls on.
 * - The story: the step nearest the middle of the screen is worked out here, in one place, and set as
 *   data-step on the section; CSS shows that step's text and caption from the same attribute.
 *
 * With reduced motion the finished drawing is shown, still; the story step still follows the scroll
 * (only which text is bright changes, nothing moves).
 */
(function () {
  "use strict";
  var root = document.documentElement;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var header = document.querySelector(".site-header");
  var hero = document.querySelector(".hero");
  var heroSvg = document.querySelector('[data-breaker="hero"] svg.breaker');
  var story = document.querySelector(".story");
  var steps = story ? story.querySelectorAll(".story__step") : [];
  var exploding = false;
  var queued = false;

  /* Parts in drawing order: the frame first, then outwards. */
  var ORDER = ["frame", "fixed-contacts", "moving-contacts", "arcing-contacts", "isolating-contacts",
               "rear-terminals", "slide-rails", "arc-chutes", "auxiliary-switches", "front-plate",
               "position-indicator"];
  var PART_GAP = 160;   // ms between parts
  var DRAW_END = 3200;  // ms: parts, then leaders (from 1900), then labels (from 2400)

  function measureNav() {
    if (header) root.style.setProperty("--nav-h", header.offsetHeight + "px");
  }

  function drawOn(svg, done) {
    var parts = Array.prototype.slice.call(svg.querySelectorAll(".bk-art > .bk-part"));
    parts.sort(function (a, b) {
      return ORDER.indexOf(a.dataset.part) - ORDER.indexOf(b.dataset.part);
    });
    var strokes = [];
    parts.forEach(function (part, i) {
      part.style.setProperty("--delay", i * PART_GAP + "ms");
      part.querySelectorAll("path:not(.f)").forEach(function (path) {
        var length = path.getTotalLength();
        path.style.strokeDasharray = length + " " + length;
        path.style.strokeDashoffset = String(length);
        strokes.push(path);
      });
    });
    svg.classList.add("is-drawing");
    root.classList.remove("hero-pending");  // hidden until now, so it never shows complete first
    void svg.getBoundingClientRect();  // start from the hidden state
    svg.classList.add("is-drawn");
    strokes.forEach(function (path) { path.style.strokeDashoffset = "0"; });
    window.setTimeout(function () {
      svg.classList.remove("is-drawing", "is-drawn");
      strokes.forEach(function (path) {
        path.style.strokeDasharray = "";
        path.style.strokeDashoffset = "";
      });
      done();
    }, DRAW_END);
  }

  function update() {
    queued = false;
    if (exploding && hero && heroSvg) {
      /* Progress through the pin: 0 while the hero's top is at the top bar (where the scene sticks), 1 when
         its bottom reaches the bottom of the screen and the pin releases. Open at the middle, closed at both
         ends. */
      var nav = header ? header.offsetHeight : 0;
      var box = hero.getBoundingClientRect();
      var span = Math.max(1, box.height - (window.innerHeight - nav));
      var p = Math.min(1, Math.max(0, (nav - box.top) / span));
      window.SeaBreaker.setExplode(heroSvg, Math.sin(Math.PI * p));
    }
    if (story && steps.length) {
      var middle = window.innerHeight * 0.5;
      var best = 1;
      var bestDistance = Infinity;
      for (var i = 0; i < steps.length; i++) {
        var box = steps[i].getBoundingClientRect();
        var distance = Math.abs(box.top + box.height / 2 - middle);
        if (distance < bestDistance) {
          bestDistance = distance;
          best = i + 1;
        }
      }
      if (story.dataset.step !== String(best)) story.dataset.step = String(best);
    }
  }

  function schedule() {
    if (!queued) {
      queued = true;
      window.requestAnimationFrame(update);
    }
  }

  /* The home page sets the labels larger than the drawing's own size; refit the leaders to them once
     the fonts are in, and again when the width changes (labels hidden below 1100 px come back). */
  function fitAll() {
    if (!window.SeaBreaker) return;
    document.querySelectorAll("[data-breaker] svg.breaker").forEach(window.SeaBreaker.fitLeaders);
  }

  measureNav();
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(fitAll);
  } else {
    fitAll();
  }
  window.addEventListener("resize", function () {
    measureNav();
    fitAll();
    schedule();
  });
  window.addEventListener("scroll", schedule, { passive: true });

  if (heroSvg && window.SeaBreaker && !reduce) {
    drawOn(heroSvg, function () {
      exploding = true;
      schedule();
    });
  } else {
    root.classList.remove("hero-pending");
  }
  schedule();
})();
