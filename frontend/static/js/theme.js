/*
 * The theme switch in the top bar: dark (the default) or light.
 *
 * The choice is the data-theme attribute on <html>. base.html applies the stored choice before the
 * page paints; this script shows the switch, flips the attribute and stores it. Storage can be
 * blocked (private windows, strict settings): every read and write is wrapped, and the page works
 * without it, in the dark theme.
 */
(function () {
  "use strict";
  var KEY = "sea-theme";
  var root = document.documentElement;

  function current() {
    return root.dataset.theme === "light" ? "light" : "dark";
  }

  function label(button) {
    var other = current() === "dark" ? "light" : "dark";
    button.setAttribute("aria-label", "Switch to " + other + " theme");
    button.setAttribute("title", "Switch to " + other + " theme");
  }

  function apply(theme) {
    root.dataset.theme = theme;
    try {
      localStorage.setItem(KEY, theme);
    } catch (e) {
      /* storage blocked: the choice lasts for this page only */
    }
    document.querySelectorAll("[data-theme-toggle]").forEach(label);
    document.dispatchEvent(new CustomEvent("themechange", { detail: { theme: theme } }));
  }

  document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
    button.hidden = false;
    label(button);
    button.addEventListener("click", function () {
      apply(current() === "dark" ? "light" : "dark");
    });
  });
})();
