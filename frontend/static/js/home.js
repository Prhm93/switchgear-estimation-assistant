/*
 * Home page motion, written by hand (no library).
 *
 * - The statement: as it scrolls through the screen its words brighten in reading order. Every word
 *   is in the HTML and readable before that; only the colour changes.
 * - How it works: the switchboard line drawing draws itself with the scroll (stroke-dashoffset,
 *   driven by the --draw custom property, 0 to 1).
 *
 * Work is done only while a part is on screen (IntersectionObserver) and at most once per frame.
 * With reduced motion, or without IntersectionObserver, nothing moves and everything is shown.
 */
(function () {
  "use strict";
  var root = document.documentElement;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce || !("IntersectionObserver" in window)) {
    root.classList.remove("js");
    return;
  }

  var statement = document.querySelector(".statement");
  var words = statement ? statement.querySelectorAll(".word") : [];
  var figure = document.querySelector(".how__figure");
  var visible = new Set();
  var queued = false;

  /* 0 when the top of el reaches the bottom of the screen, 1 when its middle reaches 40 % from the top. */
  function progress(el) {
    var box = el.getBoundingClientRect();
    var screen = window.innerHeight || 1;
    var span = screen * 0.6 + box.height * 0.5;
    return Math.min(1, Math.max(0, (screen - box.top) / span));
  }

  function update() {
    queued = false;
    if (statement && visible.has(statement)) {
      var lit = Math.round(progress(statement) * words.length);
      for (var i = 0; i < words.length; i++) {
        words[i].classList.toggle("is-on", i < lit);
      }
    }
    if (figure && visible.has(figure)) {
      figure.style.setProperty("--draw", progress(figure).toFixed(3));
    }
  }

  function schedule() {
    if (!queued) {
      queued = true;
      window.requestAnimationFrame(update);
    }
  }

  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        visible.add(entry.target);
      } else {
        visible.delete(entry.target);
      }
    });
    schedule();
  });
  if (statement) observer.observe(statement);
  if (figure) observer.observe(figure);
  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", schedule);
})();
