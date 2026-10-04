(function () {
  const nav = document.getElementById("tabs");
  const panels = Array.prototype.slice.call(document.querySelectorAll("[data-panel]"));
  const buttons = Array.prototype.slice.call(nav.querySelectorAll("[data-tab]"));

  function show(name) {
    buttons.forEach(function (button) {
      button.setAttribute("aria-selected", button.getAttribute("data-tab") === name ? "true" : "false");
    });
    panels.forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-panel") !== name;
    });
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, "", "#" + name);
    }
  }

  nav.addEventListener("click", function (event) {
    const button = event.target.closest("[data-tab]");
    if (!button) return;
    show(button.getAttribute("data-tab"));
  });

  const hash = (window.location.hash || "").replace("#", "");
  const start = buttons.some(function (button) { return button.getAttribute("data-tab") === hash; })
    ? hash
    : "benchmark";
  show(start);
})();
