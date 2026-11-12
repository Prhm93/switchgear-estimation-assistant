/*
 * Drag and drop for the upload form. Without this script the form still works:
 * choose files, then press the button. With it, files dropped on the card are
 * put into the file input and sent at once (through HTMX when the form uses it).
 *
 * The home page's form (data-file-picker) never sends at once: chosen and dropped files are listed, each
 * with a Remove link, "Add files" becomes "Add more", and reading starts only on "Read these files".
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
    if (window.htmx && form.hasAttribute("hx-post")) {
      window.htmx.trigger(form, "submit");
    } else if (form.requestSubmit) {
      form.requestSubmit();
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
      /* A form with other fields to fill (the new-enquiry name) waits for its Start button. */
      if (!form.querySelector('input[type="text"], input:not([type])[name="name"]')) submit(form);
    });
    form.addEventListener("htmx:afterRequest", function () {
      form.reset();
      summary(form, []);
    });
  }

  function size(bytes) {
    return bytes < 1024 * 1024 ? Math.max(1, Math.round(bytes / 1024)) + " kB" : (bytes / 1048576).toFixed(1) + " MB";
  }

  /* The list of chosen files: kept here, copied into the file input with a DataTransfer on every change. */
  function initPicker(form) {
    var input = form.querySelector("[data-file-input]");
    var list = form.querySelector("[data-file-list]");
    var read = form.querySelector("[data-read]");
    var label = form.querySelector("[data-add-label]");
    var text = form.querySelector("[data-add-text]");
    if (!input || !list || !read) return;
    var canList = typeof window.DataTransfer === "function";
    var chosen = [];

    function render() {
      list.textContent = "";
      chosen.forEach(function (file, i) {
        var item = document.createElement("li");
        item.className = "file-pick";
        var name = document.createElement("span");
        name.textContent = file.name + " (" + size(file.size) + ")";
        var remove = document.createElement("a");
        remove.href = "#";
        remove.setAttribute("data-remove", String(i));
        remove.textContent = "Remove";
        remove.setAttribute("aria-label", "Remove " + file.name);
        item.appendChild(name);
        item.appendChild(remove);
        list.appendChild(item);
      });
      read.hidden = !chosen.length;
      if (text) text.textContent = chosen.length ? "Add more" : "Add files";
      if (label) {
        label.classList.toggle("btn--primary", !chosen.length);
        label.classList.toggle("btn--secondary", chosen.length > 0);
      }
    }

    function sync() {
      if (canList) {
        var transfer = new DataTransfer();
        chosen.forEach(function (file) { transfer.items.add(file); });
        input.files = transfer.files;
      }
      render();
    }

    function add(files) {
      Array.prototype.forEach.call(files, function (file) {
        var seen = chosen.some(function (c) { return c.name === file.name && c.size === file.size; });
        if (!seen) chosen.push(file);
      });
      sync();
    }

    input.addEventListener("change", function () {
      if (canList) {
        add(input.files);
      } else {  /* an old browser: the last choice only, still sent on "Read these files" */
        chosen = Array.prototype.slice.call(input.files);
        render();
      }
    });
    list.addEventListener("click", function (event) {
      var link = event.target.closest("[data-remove]");
      if (!link) return;
      event.preventDefault();
      chosen.splice(Number(link.getAttribute("data-remove")), 1);
      sync();
    });
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
      if (event.dataTransfer && event.dataTransfer.files.length && canList) add(event.dataTransfer.files);
    });
    form.addEventListener("submit", function (event) {
      if (!chosen.length) event.preventDefault();  /* nothing to read yet */
    });
    render();
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-dropzone]").forEach(init);
    document.querySelectorAll("[data-file-picker]").forEach(initPicker);
  });
})();
