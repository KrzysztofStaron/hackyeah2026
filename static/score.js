(function () {
  const SERIES = [
    { key: "score", label: "score", color: "#3f6212" },
    { key: "false_positive", label: "false_positive", color: "#92400e" },
    { key: "false_negative", label: "false_negative", color: "#9f1239" }
  ];

  function point(value, index, planned, plot) {
    if (value == null || !planned) return "";
    const x = plot.left + ((index + 1) / planned) * plot.width;
    const y = plot.top + (1 - value / 100) * plot.height;
    return x.toFixed(1) + "," + y.toFixed(1);
  }

  function line(history, key, planned, plot) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    const dots = [];
    history.forEach(function (row, index) {
      const placed = point(row[key], index, planned, plot);
      if (placed) dots.push(placed);
    });
    path.setAttribute("points", dots.join(" "));
    path.setAttribute("fill", "none");
    path.setAttribute("stroke-width", "2");
    path.setAttribute("stroke-linejoin", "round");
    path.setAttribute("stroke-linecap", "round");
    return path;
  }

  function grid(svg, plot) {
    [0, 50, 100].forEach(function (mark) {
      const y = plot.top + (1 - mark / 100) * plot.height;
      const rule = document.createElementNS("http://www.w3.org/2000/svg", "line");
      rule.setAttribute("x1", String(plot.left));
      rule.setAttribute("x2", String(plot.left + plot.width));
      rule.setAttribute("y1", y.toFixed(1));
      rule.setAttribute("y2", y.toFixed(1));
      rule.setAttribute("stroke", "#e7e5e4");
      svg.appendChild(rule);
      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("x", "0");
      label.setAttribute("y", (y + 4).toFixed(1));
      label.textContent = String(mark);
      svg.appendChild(label);
    });
  }

  window.drawScore = function (svg, legend, history, planned) {
    const plot = { left: 36, top: 12, width: 590, height: 156 };
    svg.replaceChildren();
    grid(svg, plot);
    SERIES.forEach(function (series) {
      const path = line(history, series.key, planned, plot);
      path.setAttribute("stroke", series.color);
      svg.appendChild(path);
    });
    const latest = history.length ? history[history.length - 1] : null;
    legend.replaceChildren();
    SERIES.forEach(function (series) {
      const item = document.createElement("span");
      const value = latest && latest[series.key] != null ? latest[series.key].toFixed(1) : "—";
      item.textContent = series.label + " " + value;
      item.style.color = series.color;
      legend.appendChild(item);
    });
    const done = history.length;
    svg.setAttribute(
      "aria-label",
      "After " + String(done) + " of " + String(planned) + " safety cases. " + legend.textContent
    );
  };
})();
