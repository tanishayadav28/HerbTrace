/* Shared UI behaviour: toasts, loading overlay, confirm dialog, password toggle */
(function () {
  "use strict";

  // Toasts from Django messages
  document.querySelectorAll(".toast").forEach(function (el) {
    var delay = el.classList.contains("text-bg-danger") || el.classList.contains("text-bg-warning") ? 9000 : 5000;
    new bootstrap.Toast(el, { delay: delay }).show();
  });

  // Loading overlay on form submit (skipped for forms that opt out)
  var overlay = document.getElementById("loading-overlay");
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (event.defaultPrevented || form.hasAttribute("data-no-loader")) return;
      if (overlay) overlay.classList.add("show");
      form.querySelectorAll("button[type=submit]").forEach(function (b) { b.disabled = true; });
      // If the browser navigates back (bfcache) make sure the page is usable again.
      window.addEventListener("pageshow", function () {
        if (overlay) overlay.classList.remove("show");
        form.querySelectorAll("button[type=submit]").forEach(function (b) { b.disabled = false; });
      }, { once: true });
    });
  });

  // Confirmation dialog: <form data-confirm="Are you sure?">
  var modalEl = document.getElementById("confirm-modal");
  if (modalEl) {
    var modal = new bootstrap.Modal(modalEl);
    var pendingForm = null;
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (form.dataset.confirmed === "1") return;
        event.preventDefault();
        event.stopImmediatePropagation();
        pendingForm = form;
        modalEl.querySelector(".confirm-text").textContent = form.dataset.confirm;
        var ok = modalEl.querySelector(".confirm-ok");
        ok.textContent = form.dataset.confirmLabel || "Confirm";
        ok.className = "btn confirm-ok " + (form.dataset.confirmClass || "btn-leaf");
        modal.show();
      }, true);
    });
    modalEl.querySelector(".confirm-ok").addEventListener("click", function () {
      if (pendingForm) {
        pendingForm.dataset.confirmed = "1";
        modal.hide();
        pendingForm.requestSubmit();
      }
    });
  }

  // Password show / hide
  document.querySelectorAll("[data-toggle-password]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.querySelector(btn.dataset.togglePassword);
      if (!input) return;
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.setAttribute("aria-pressed", show ? "true" : "false");
      btn.querySelector("i").className = show ? "bi bi-eye-slash" : "bi bi-eye";
    });
  });
})();
