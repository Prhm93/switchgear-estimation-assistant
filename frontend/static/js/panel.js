/*
 * The proof panel. A value or an item is a link that loads its proof into
 * the panel with HTMX; without this script (or without HTMX) the same link
 * opens the proof as its own page. This script only closes the panel and the
 * small menus: the close button, the Escape key, and a click outside a menu.
 */
(function () {
  "use strict";

  function closePanel() {
    var panel = document.getElementById("panel");
    if (panel && panel.firstElementChild) {
      panel.innerHTML = "";
      return true;
    }
    return false;
  }

  document.addEventListener("click", function (event) {
    var close = event.target.closest("[data-panel-close]");
    if (close && document.getElementById("panel") && close.closest("#panel")) {
      event.preventDefault();
      closePanel();
      return;
    }
    document.querySelectorAll("details.menu[open]").forEach(function (menu) {
      if (!menu.contains(event.target)) menu.removeAttribute("open");
    });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    var open = document.querySelector("details.menu[open]");
    if (open) {
      open.removeAttribute("open");
      var summary = open.querySelector("summary");
      if (summary) summary.focus();
      return;
    }
    closePanel();
  });

  /* After a panel loads, bring it into view on narrow screens and move focus to its heading. */
  document.addEventListener("htmx:afterSwap", function (event) {
    if (event.target && event.target.id === "panel" && event.target.firstElementChild) {
      var title = event.target.querySelector(".panel__title");
      if (title) {
        title.setAttribute("tabindex", "-1");
        title.focus({ preventScroll: true });
      }
      if (window.matchMedia("(max-width: 900px)").matches) event.target.scrollIntoView({ block: "start" });
    }
  });
})();
