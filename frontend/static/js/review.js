/*
 * Review cards: keep "Approve N ticked" in step with the ticks. Without this script the button keeps the
 * first count, and the form still sends exactly the ticked values.
 */
(function () {
  "use strict";
  document.addEventListener("change", function (event) {
    var box = event.target;
    if (!box.matches || !box.matches("[data-tick]")) return;
    var form = box.closest("[data-tick-form]");
    var out = form && form.querySelector("[data-ticked]");
    if (out) out.textContent = form.querySelectorAll("[data-tick]:checked").length;
  });
})();
