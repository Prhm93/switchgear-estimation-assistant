/*
 * Accessible tabs, following the WAI-ARIA Authoring Practices tabs pattern.
 *
 * Markup: an element with role="tablist" containing buttons with role="tab",
 * aria-controls pointing at elements with role="tabpanel". Left/Right move
 * between tabs, Home/End jump to the ends; only the active tab is in the tab
 * order. Works without this script too: all panels are then visible.
 */
(function () {
  "use strict";

  function activate(tablist, tab) {
    tablist.querySelectorAll('[role="tab"]').forEach(function (other) {
      var selected = other === tab;
      other.setAttribute("aria-selected", String(selected));
      other.tabIndex = selected ? 0 : -1;
      var panel = document.getElementById(other.getAttribute("aria-controls"));
      if (panel) panel.hidden = !selected;
    });
  }

  function init(tablist) {
    var tabs = Array.prototype.slice.call(tablist.querySelectorAll('[role="tab"]'));
    var current = tabs.find(function (t) { return t.getAttribute("aria-selected") === "true"; }) || tabs[0];
    activate(tablist, current);

    tablist.addEventListener("click", function (event) {
      var tab = event.target.closest('[role="tab"]');
      if (tab) activate(tablist, tab);
    });

    tablist.addEventListener("keydown", function (event) {
      var index = tabs.indexOf(document.activeElement);
      if (index < 0) return;
      var next = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: tabs.length - 1 }[event.key];
      if (next === undefined) return;
      event.preventDefault();
      var tab = tabs[(next + tabs.length) % tabs.length];
      activate(tablist, tab);
      tab.focus();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll('[role="tablist"]').forEach(init);
  });
})();
