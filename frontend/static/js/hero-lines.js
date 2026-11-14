/*
 * The home page hero background: a faint grid and thin contour lines on a 2D canvas.
 *
 * Strokes only, no filled shapes. The colours are the theme tokens --hero-grid, --hero-line and
 * --hero-line-strong, read again when the theme switches. The lines drift slowly with time and with
 * the scroll.
 *
 * Cost guards: the pixel ratio is capped at 1.5 and at most 30 frames a second are drawn; nothing is
 * drawn while the tab is hidden or the hero is off screen. With reduced motion one still frame is drawn.
 * window.SeaHeroLines counts the frames drawn and the time spent drawing them (performance.now), so
 * the cost can be measured in the browser.
 */
(function () {
  "use strict";
  // The pinned scene when there is one (stage-hero-pin), so the canvas is one screen, not the whole scroll area.
  var hero = document.querySelector(".hero__scene") || document.querySelector(".hero");
  if (!hero) return;
  var canvas = document.createElement("canvas");
  var ctx = canvas.getContext("2d");
  if (!ctx) return;
  canvas.className = "hero__canvas";
  canvas.setAttribute("aria-hidden", "true");
  hero.insertBefore(canvas, hero.firstChild);

  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var dpr = Math.min(window.devicePixelRatio || 1, 1.5);
  var width = 0;
  var height = 0;
  var colours = { grid: "", line: "", strong: "" };
  var frame = 0;
  var last = 0;
  var onScreen = true;
  var stats = { frames: 0, drawMs: 0 };
  window.SeaHeroLines = stats;

  function readColours() {
    var style = window.getComputedStyle(document.documentElement);
    colours.grid = style.getPropertyValue("--hero-grid").trim();
    colours.line = style.getPropertyValue("--hero-line").trim();
    colours.strong = style.getPropertyValue("--hero-line-strong").trim();
  }

  function resize() {
    var box = hero.getBoundingClientRect();
    width = box.width;
    height = box.height;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  /* One frame: the 64 px grid, then 34 contour lines bent around a point right of centre. */
  function draw(now) {
    var started = performance.now();
    var t = now * 0.00012;
    var scroll = reduce ? 0 : (window.scrollY || 0) * 0.00045;
    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = colours.grid;
    ctx.lineWidth = 0.7;
    ctx.beginPath();
    for (var gx = 0; gx <= width; gx += 64) {
      ctx.moveTo(Math.round(gx) + 0.5, 0);
      ctx.lineTo(Math.round(gx) + 0.5, height);
    }
    for (var gy = 0; gy <= height; gy += 64) {
      ctx.moveTo(0, Math.round(gy) + 0.5);
      ctx.lineTo(width, Math.round(gy) + 0.5);
    }
    ctx.stroke();

    var originX = width * 0.7;
    var originY = height * 0.47;
    for (var k = -12; k < 22; k++) {
      var y0 = originY + k * 22;
      ctx.beginPath();
      for (var x = -20; x < width + 40; x += 5) {
        var phase = x * 0.008 + t + scroll;
        var displaced = Math.sin(phase + k * 0.24) * 25 + Math.sin(phase * 0.54 - k * 0.31) * 35;
        var bend = Math.exp(-Math.pow((x - originX) / (width * 0.43), 2)) * Math.sin(k * 0.38 + t * 0.4) * 62;
        var y = y0 + displaced + bend + Math.sin(x * 0.002 + k * 0.23) * 26;
        if (x === -20) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      }
      var major = k % 5 === 0;
      ctx.lineWidth = major ? 1.1 : 0.65;
      ctx.strokeStyle = major ? colours.strong : colours.line;
      ctx.stroke();
    }
    stats.frames += 1;
    stats.drawMs += performance.now() - started;
  }

  function loop(now) {
    frame = window.requestAnimationFrame(loop);
    if (now - last < 1000 / 30 - 1) return;  // at most 30 frames a second
    last = now;
    draw(now);
  }

  function start() {
    if (!frame && onScreen && !document.hidden) frame = window.requestAnimationFrame(loop);
  }

  function stop() {
    if (frame) window.cancelAnimationFrame(frame);
    frame = 0;
  }

  readColours();
  resize();
  window.addEventListener("resize", function () {
    resize();
    draw(last);
  });
  document.addEventListener("themechange", function () {
    readColours();
    draw(last);
  });

  if (reduce) {
    draw(0);  // one still frame, no loop
    return;
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      stop();
    } else {
      start();
    }
  });
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      onScreen = entries[entries.length - 1].isIntersecting;
      if (onScreen) {
        start();
      } else {
        stop();
      }
    }).observe(hero);
  }
  start();
})();
