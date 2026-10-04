(function () {
  function render(data) {
    const loaded = document.getElementById("loaded");
    if (loaded) {
      loaded.textContent = "Profile " + data.profile + " · loaded " + data.loaded_at;
    }

    fillMetrics(document.getElementById("metrics"), data);
    fillMetrics(document.getElementById("desk-metrics"), data);
    fillThreats(data.threats || []);
    fillBudget(data.budget || []);
    fillEvents(document.getElementById("events"), data.events || []);
    fillEvents(document.getElementById("desk-events"), data.events || []);
  }

  function fillMetrics(root, data) {
    if (!root) return;
    root.replaceChildren(
      metric("Requests", data.requests),
      metric("Allowed", data.allowed),
      metric("Blocked", data.blocked),
      metric("Redacted", data.redacted)
    );
  }

  function fillEvents(root, events) {
    if (!root) return;
    root.replaceChildren();
    events.slice().reverse().forEach(function (event) {
      const row = document.createElement("tr");
      row.className = "log-" + String(event.decision || "allow");
      [
        event.when || event.ts || "",
        event.agent || "",
        event.what || event.decision || "",
        event.why || event.check || "",
        event.latency || (event.latency_ms == null ? "" : event.latency_ms + " ms"),
        event.spend || (event.usd == null ? "" : "$" + event.usd)
      ].forEach(function (value) {
        const cell = document.createElement("td");
        cell.textContent = value == null ? "" : String(value);
        row.appendChild(cell);
      });
      root.appendChild(row);
    });
  }

  function fillThreats(rows) {
    const root = document.getElementById("threats");
    if (!root) return;
    root.replaceChildren();
    rows.forEach(function (row) {
      const line = document.createElement("p");
      const name = document.createElement("span");
      name.textContent = row.label;
      const count = document.createElement("b");
      count.textContent = String(row.count);
      line.append(name, count);
      root.appendChild(line);
    });
  }

  function fillBudget(rows) {
    const root = document.getElementById("budget");
    if (!root) return;
    root.replaceChildren();
    rows.forEach(function (row) {
      const cap = Number(row.usd_cap) || 0;
      const usd = Number(row.usd) || 0;
      const pct = cap === 0 ? 100 : Math.min(100, Math.round((usd / cap) * 1000) / 10);
      const title = document.createElement("p");
      title.textContent = "$" + usd.toFixed(2) + " / $" + cap.toFixed(2);
      const bar = document.createElement("div");
      bar.className = "bar";
      const fill = document.createElement("span");
      fill.style.width = String(pct) + "%";
      bar.appendChild(fill);
      const note = document.createElement("p");
      note.className = "meta";
      note.textContent = row.agent + " · " + String(pct) + "%";
      root.append(title, bar, note);
    });
  }

  function metric(label, value) {
    const node = document.createElement("article");
    node.className = "metric";
    const number = document.createElement("b");
    number.textContent = value == null ? "0" : String(value);
    const caption = document.createElement("span");
    caption.textContent = label;
    node.append(number, caption);
    return node;
  }

  function load() {
    return fetch("/v1/report").then(function (response) {
      return response.json();
    }).then(render);
  }

  fetch("/v1/demo/audit/reset", { method: "POST" }).then(load);
  setInterval(load, 2000);
})();
