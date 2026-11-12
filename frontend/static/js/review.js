/*
 * Review cards: keep "(N ticked)" in step with the tick boxes. A tick box may sit outside its form (form="..."),
 * so the count goes through the form's own elements. Without this script the button keeps the first count, and
 * the form still sends exactly the ticked values.
 */
(function () {
  "use strict";
  document.addEventListener("change", function (event) {
    var box = event.target;
    if (!box.matches || !box.matches("[data-tick]") || !box.form) return;
    var out = box.form.querySelector("[data-ticked]");
    if (!out) return;
    out.textContent = Array.prototype.filter.call(box.form.elements, function (el) {
      return el.matches("[data-tick]") && el.checked;
    }).length;
  });
})();
