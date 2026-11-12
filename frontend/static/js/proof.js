/*
 * Proof viewer: one value at a time, linked both ways.
 *
 * Selecting a box on the drawing (a click, or Enter on a focused box) marks its value card under "Read on this
 * sheet", scrolls the card into view and shows the box enlarged next to the drawing with the value read under it.
 * "Show on the drawing" on a card marks and pulses its box and marks its line in the text panel. Only one box and
 * one card are active at a time. Without this script the links still jump between box and card (#box-N, #v-N).
 */
(function (root) {
  "use strict";
  var ZOOM = 3;       // the enlarged crop is about three times the size of the box on the drawing
  var UPRIGHT = 1.5;  // a box this much taller than wide holds vertical text: its crop is turned upright

  /*
   * What the enlarged crop shows and how wide it is drawn: the (already padded) box with one more padding of
   * drawing around it, turned a quarter clockwise when the text runs up the page. ``scale`` is screen pixels per
   * sheet unit, so ``width`` is about three times the region's size on screen.
   */
  function zoomView(box, scale) {
    var x = box.x - box.pad, y = box.y - box.pad, w = box.w + 2 * box.pad, h = box.h + 2 * box.pad;
    var turned = box.h > box.w * UPRIGHT;
    var across = turned ? h : w;
    return {
      viewBox: "0 0 " + across + " " + (turned ? w : h),
      transform: (turned ? "translate(" + h + " 0) rotate(90) " : "") + "translate(" + (-x) + " " + (-y) + ")",
      width: Math.round(across * scale * ZOOM),
      turned: turned
    };
  }

  function quiet() {
    return !!(root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function clear(doc) {
    Array.prototype.forEach.call(doc.querySelectorAll(".is-active, .is-pulse"), function (el) {
      el.classList.remove("is-active");
      el.classList.remove("is-pulse");
      el.removeAttribute("aria-current");
    });
  }

  function number(el, name) { return parseFloat(el.getAttribute(name)) || 0; }

  function showZoom(doc, box) {
    var panel = doc.getElementById("sheet-zoom");
    if (!panel || !box) return;
    var svg = panel.querySelector("svg"), turn = panel.querySelector("g"), frame = panel.querySelector("rect");
    var out = panel.querySelector("[data-zoom-value]"), img = doc.querySelector(".sheet__img");
    var full = number(panel, "data-width");
    var b = { x: number(box, "data-x"), y: number(box, "data-y"), w: number(box, "data-w"), h: number(box, "data-h"),
              pad: number(box, "data-pad") };
    var view = zoomView(b, img && img.clientWidth && full ? img.clientWidth / full : 1);
    svg.setAttribute("viewBox", view.viewBox);
    svg.style.width = view.width + "px";
    turn.setAttribute("transform", view.transform);
    frame.setAttribute("x", b.x); frame.setAttribute("y", b.y);
    frame.setAttribute("width", b.w); frame.setAttribute("height", b.h);
    panel.setAttribute("data-tone", box.getAttribute("data-tone") || "rules");
    out.textContent = box.getAttribute("data-read") + (view.turned ? " (turned upright)" : "");
    panel.hidden = false;
  }

  /* Mark value ``id`` everywhere: its box, its card and its text line. ``from`` is "box" or "card". */
  function select(id, from) {
    var doc = root.document;
    var box = doc.getElementById("box-" + id), card = doc.getElementById("v-" + id);
    var how = { block: "nearest", behavior: quiet() ? "auto" : "smooth" };
    clear(doc);
    if (box) {
      box.classList.add("is-active");
      if (from === "card") {
        box.getBoundingClientRect();  // restarts the pulse when the same box is shown twice
        box.classList.add("is-pulse");
        box.scrollIntoView(how);
      }
    }
    if (card) {
      card.classList.add("is-active");
      card.setAttribute("aria-current", "true");
      if (from === "box") card.scrollIntoView(how);
    }
    Array.prototype.forEach.call(doc.querySelectorAll("[data-values]"), function (mark) {
      if (mark.getAttribute("data-values").split(" ").indexOf(String(id)) >= 0) mark.classList.add("is-active");
    });
    showZoom(doc, box);
  }

  root.document.addEventListener("click", function (event) {
    var t = event.target;
    if (!t || !t.closest) return;
    var box = t.closest("[data-box]"), show = t.closest("[data-show]");
    if (box) {
      event.preventDefault();
      select(box.getAttribute("data-box"), "box");
    } else if (show) {
      event.preventDefault();
      select(show.getAttribute("data-show"), "card");
    }
  });

  root.document.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    var box = event.target && event.target.closest && event.target.closest("[data-box]");
    if (!box) return;
    event.preventDefault();
    select(box.getAttribute("data-box"), "box");
  });

  root.SheetProof = { select: select, zoomView: zoomView };
})(window);
