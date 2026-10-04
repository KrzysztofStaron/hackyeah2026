(function () {
  let lastData = null;
  let taskFilter = "";
  let benchCache = null;
  let useCachedBenchAudit = false;

  window.setUseCachedBenchAudit = function (on) {
    useCachedBenchAudit = on === true;
    if (lastData) render(lastData);
  };

  function currentPreset() {
    if (typeof window.deskPreset === "function") {
      const preset = window.deskPreset();
      if (preset) return preset;
    }
    return "default";
  }

  function cachedAuditBucket() {
    if (!benchCache || !useCachedBenchAudit) return null;
    const bucket = benchCache.by_preset && benchCache.by_preset[currentPreset()];
    if (!bucket || !bucket.audit) return null;
    return bucket.audit;
  }

  function mergeReportEvents(liveEvents) {
    const live = liveEvents || [];
    const cached = cachedAuditBucket();
    if (!cached || !Array.isArray(cached.events) || !cached.events.length) {
      return live;
    }
    const desk = deskOnly(live);
    return desk.concat(cached.events);
  }

  function filterEvents(events) {
    if (!taskFilter) return events;
    return events.filter(function (event) {
      const task = event.task || event.bench_title || "";
      return task === taskFilter;
    });
  }

  function exportEvents(events) {
    if (!taskFilter) return events;
    return events.filter(function (event) {
      const task = event.task || event.bench_title || "";
      return task === taskFilter;
    });
  }

  function downloadBlob(filename, mime, body) {
    const url = URL.createObjectURL(new Blob([body], { type: mime }));
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  function syncExportLinks() {
    const suffix = taskFilter ? "?task=" + encodeURIComponent(taskFilter) : "";
    const text = document.getElementById("audit-export-text");
    const jsonl = document.getElementById("audit-export-jsonl");
    const cached = cachedAuditBucket();
    if (cached && cached.events && cached.events.length) {
      const benchEvents = exportEvents(cached.events);
      if (text) {
        text.setAttribute("href", "#");
        text.onclick = function (event) {
          event.preventDefault();
          const lines = benchEvents.map(function (item) {
            return [
              item.when || item.ts || "",
              item.task || "",
              item.agent || "",
              item.what || item.decision || "",
              item.why || item.check || "",
              item.latency || "",
              item.spend || ""
            ].join("\t");
          });
          downloadBlob("audit-benchmark.txt", "text/plain;charset=utf-8", lines.join("\n") + "\n");
        };
      }
      if (jsonl) {
        jsonl.setAttribute("href", "#");
        jsonl.onclick = function (event) {
          event.preventDefault();
          const body = benchEvents.map(function (item) {
            return JSON.stringify(item);
          }).join("\n");
          downloadBlob("audit-benchmark.jsonl", "application/x-ndjson", body ? body + "\n" : "");
        };
      }
      return;
    }
    if (text) {
      text.onclick = null;
      text.setAttribute("href", "/v1/audit/export" + suffix);
    }
    if (jsonl) {
      jsonl.onclick = null;
      jsonl.setAttribute("href", "/v1/audit/export?format=jsonl" + (taskFilter ? "&task=" + encodeURIComponent(taskFilter) : ""));
    }
  }

  function deskOnly(events) {
    return events.filter(function (event) {
      const task = event.task || event.bench_title || "";
      return task === "Desk";
    });
  }

  function render(data) {
    lastData = data;
    const loaded = document.getElementById("loaded");
    const cached = cachedAuditBucket();
    const all = mergeReportEvents(data.events || []);
    const benchEvents = filterEvents(all.filter(function (event) {
      const task = event.task || event.bench_title || "";
      return task !== "Desk";
    }));
    const deskEvents = filterEvents(deskOnly(all));
    const metricsData = cached && !taskFilter
      ? {
          requests: cached.requests,
          allowed: cached.allowed,
          blocked: cached.blocked,
          redacted: cached.redacted
        }
      : data;
    if (loaded) {
      const total = metricsData.requests == null ? benchEvents.length : metricsData.requests;
      const cacheNote = cached && benchCache.generated_at
        ? " · cached bench audit " + benchCache.generated_at
        : "";
      loaded.textContent = "Profile " + data.profile + " · loaded " + data.loaded_at
        + " · " + String(total) + " logged (showing " + String(benchEvents.length) + " bench rows)"
        + cacheNote;
    }

    fillMetrics(document.getElementById("metrics"), metricsData, benchEvents);
    fillMetrics(document.getElementById("desk-metrics"), data, deskEvents);
    fillThreats(cached && !taskFilter && cached.threats ? cached.threats : (data.threats || []));
    fillBudget(data.budget || []);
    fillEvents(document.getElementById("events"), benchEvents);
    fillEvents(document.getElementById("desk-events"), deskEvents);
    syncExportLinks();
  }

  function fillMetrics(root, data, filtered) {
    if (!root) return;
    if (taskFilter && filtered) {
      let blocked = 0;
      let redacted = 0;
      let allowed = 0;
      filtered.forEach(function (event) {
        const decision = event.decision || "";
        if (decision === "block") blocked += 1;
        else if (decision === "redact") redacted += 1;
        else if (decision === "allow") allowed += 1;
      });
      root.replaceChildren(
        metric("Requests", blocked + redacted + allowed),
        metric("Allowed", allowed),
        metric("Blocked", blocked),
        metric("Redacted", redacted)
      );
      return;
    }
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
    if (!events.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 7;
      cell.className = "meta";
      cell.textContent = useCachedBenchAudit
        ? "No cached audit for this preset. Run scripts/run_bench_cache.py to regenerate static/bench_cache.json."
        : "No events yet. Run the benchmark or send a desk prompt to populate the log.";
      row.appendChild(cell);
      root.appendChild(row);
      return;
    }
    events.slice().reverse().forEach(function (event) {
      const row = document.createElement("tr");
      row.className = "log-" + String(event.decision || "allow");
      [
        event.when || event.ts || "",
        event.task || event.bench_title || "",
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

  function paintTaskFilter(book) {
    const select = document.getElementById("audit-task-filter");
    if (!select) return;
    const titles = [];
    (book.cases || []).forEach(function (item) {
      if (!item.title || titles.indexOf(item.title) !== -1) return;
      titles.push(item.title);
    });
    titles.sort();
    select.replaceChildren();
    const all = document.createElement("option");
    all.value = "";
    all.textContent = "All tasks";
    select.appendChild(all);
    const desk = document.createElement("option");
    desk.value = "Desk";
    desk.textContent = "Desk";
    select.appendChild(desk);
    titles.forEach(function (title) {
      const option = document.createElement("option");
      option.value = title;
      option.textContent = title;
      select.appendChild(option);
    });
    if (!select.dataset.ready) {
      select.dataset.ready = "1";
      select.addEventListener("change", function () {
        taskFilter = select.value;
        if (lastData) render(lastData);
      });
    }
  }

  fetch("/assets/bench_cache.json").then(function (response) {
    if (!response.ok) return null;
    return response.json();
  }).then(function (cache) {
    if (cache && cache.by_preset) {
      benchCache = cache;
      if (lastData) render(lastData);
    }
  });

  fetch("/assets/bench.json").then(function (response) {
    return response.json();
  }).then(paintTaskFilter);

  load();
  setInterval(load, 2000);
})();
