(function () {
  const CHEVRON = Array.from({ length: 9 }, function (_, i) {
    const r = Math.floor(i / 3);
    const c = i % 3;
    return (c + Math.abs(r - 1)) * 90;
  });

  const ORBIT_ORDER = [0, 1, 2, 5, 8, 7, 6, 3];
  const ORBIT = Array.from({ length: 9 }, function (_, i) {
    const k = ORBIT_ORDER.indexOf(i);
    return k === -1 ? null : k * 110;
  });

  const PATTERNS = {
    Drive: { delays: CHEVRON, dur: 650, round: false },
    Dots: { delays: CHEVRON, dur: 650, round: true },
    Orbit: { delays: ORBIT, dur: 950, round: false }
  };

  function grid(pattern) {
    const node = document.createElement("span");
    node.className = "loading-grid";
    node.setAttribute("aria-hidden", "true");
    pattern.delays.forEach(function (delay) {
      const cell = document.createElement("span");
      cell.className = "loading-pixel" + (pattern.round ? " is-round" : "");
      if (delay === null) {
        cell.style.opacity = "0.07";
      } else {
        cell.style.opacity = "0.15";
        cell.style.animation = "pixel-on " + pattern.dur + "ms ease-in-out " + delay + "ms infinite";
      }
      node.appendChild(cell);
    });
    return node;
  }

  function formatElapsed(ds) {
    const total = ds / 10;
    if (total < 60) return total.toFixed(1) + "s";
    return Math.floor(total / 60) + "m " + (total % 60).toFixed(1) + "s";
  }

  function loadingState(options) {
    const opts = options || {};
    const variant = opts.variant || "Drive";
    const pattern = PATTERNS[variant] || PATTERNS.Drive;
    const label = opts.label || "Churning";

    const root = document.createElement("div");
    root.className = "loading-state";
    root.setAttribute("role", "status");

    const labelEl = document.createElement("span");
    labelEl.className = "loading-label";
    labelEl.textContent = label;

    const elapsedEl = document.createElement("span");
    elapsedEl.className = "loading-elapsed";
    elapsedEl.textContent = "0.0s";

    root.append(grid(pattern), labelEl, elapsedEl);

    let ds = 0;
    const timer = setInterval(function () {
      ds += 1;
      elapsedEl.textContent = formatElapsed(ds);
    }, 100);

    root.stop = function () {
      clearInterval(timer);
    };
    return root;
  }

  window.loadingState = loadingState;
})();
