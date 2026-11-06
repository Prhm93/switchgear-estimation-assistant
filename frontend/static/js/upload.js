/*
 * Drag and drop for the upload form. Without this script the form still works:
 * choose files, then press Upload. With it, files dropped on the card are put
 * into the file input and uploaded at once (through HTMX when it is loaded).
 */
(function () {
  "use strict";

  function summary(form, files) {
    var out = form.querySelector("[data-file-summary]");
    if (!out) return;
    var names = Array.prototype.map.call(files, function (f) { return f.name; });
    out.textContent = names.length ? names.length + " selected: " + names.join(", ") : "";
  }

  function submit(form) {
    if (window.htmx) {
      window.htmx.trigger(form, "submit");
    } else {
      form.submit();
    }
  }

  function init(form) {
    var input = form.querySelector("[data-file-input]");
    if (!input) return;
    input.addEventListener("change", function () { summary(form, input.files); });

    ["dragenter", "dragover"].forEach(function (name) {
      form.addEventListener(name, function (event) {
        event.preventDefault();
        form.classList.add("dropzone--over");
      });
    });
    ["dragleave", "drop"].forEach(function (name) {
      form.addEventListener(name, function (event) {
        event.preventDefault();
        form.classList.remove("dropzone--over");
      });
    });
    form.addEventListener("drop", function (event) {
      if (!event.dataTransfer || !event.dataTransfer.files.length) return;
      input.files = event.dataTransfer.files;
      summary(form, input.files);
      submit(form);
    });
    form.addEventListener("htmx:afterRequest", function () {
      form.reset();
      summary(form, []);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-dropzone]").forEach(init);
  });
})();
