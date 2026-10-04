(function () {
  const statusNodes = Array.prototype.slice.call(document.querySelectorAll("[data-settings-status]"));
  const presetRoots = Array.prototype.slice.call(document.querySelectorAll("[data-presets]"));
  const controlTables = Array.prototype.slice.call(document.querySelectorAll("[data-controls]"));
  const modes = ["disabled", "redact", "strict"];
  let current = null;

  function setStatus(text) {
    statusNodes.forEach(function (node) {
      node.textContent = text;
    });
  }

  function paintPresets(data) {
    presetRoots.forEach(function (root) {
      root.replaceChildren();
      data.presets.forEach(function (preset) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = preset.label;
        button.setAttribute("aria-pressed", data.preset === preset.id ? "true" : "false");
        button.addEventListener("click", function () {
          commit({ preset: preset.id });
        });
        root.appendChild(button);
      });
    });
  }

  function paintTable(table, data) {
    table.replaceChildren();
    const head = document.createElement("tr");
    ["Control", "Mode", "What this mode does"].forEach(function (label) {
      const cell = document.createElement("th");
      cell.textContent = label;
      head.appendChild(cell);
    });
    table.appendChild(head);
    data.controls.forEach(function (item) {
      const row = document.createElement("tr");
      row.title = item.tip;
      const name = document.createElement("td");
      name.textContent = item.label;
      const choice = document.createElement("td");
      const select = document.createElement("select");
      modes.forEach(function (mode) {
        const option = document.createElement("option");
        option.value = mode;
        option.textContent = mode;
        if (mode === item.mode) option.selected = true;
        select.appendChild(option);
      });
      const note = document.createElement("td");
      note.textContent = item.explains[item.mode];
      select.addEventListener("change", function () {
        item.mode = select.value;
        note.textContent = item.explains[select.value];
        save();
      });
      choice.appendChild(select);
      row.append(name, choice, note);
      table.appendChild(row);
    });
    const budget = document.createElement("tr");
    const budgetName = document.createElement("td");
    budgetName.textContent = "Budget ( $ )";
    const budgetChoice = document.createElement("td");
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.step = "0.01";
    input.value = String(data.usd_cap);
    const budgetNote = document.createElement("td");
    budgetNote.textContent = "Stops the agent when spend reaches this amount.";
    input.addEventListener("change", function () {
      data.usd_cap = Number(input.value);
      save();
    });
    budgetChoice.appendChild(input);
    budget.append(budgetName, budgetChoice, budgetNote);
    table.appendChild(budget);
    table.appendChild(confidenceRow(data));
  }

  function paint(data) {
    current = data;
    controlTables.forEach(function (table) {
      paintTable(table, data);
    });
    paintPresets(data);
  }

  function confidenceRow(data) {
    const row = document.createElement("tr");
    const name = document.createElement("td");
    name.textContent = "Require high confidence";
    const choice = document.createElement("td");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = data.require_high_confidence === true;
    const note = document.createElement("td");
    note.textContent = "Stops the agent when Jev is under 80% confident the action is safe.";
    input.addEventListener("change", function () {
      data.require_high_confidence = input.checked;
      save();
    });
    choice.appendChild(input);
    row.append(name, choice, note);
    return row;
  }

  function save() {
    const controls = {};
    current.controls.forEach(function (item) {
      controls[item.id] = item.mode;
    });
    commit({
      controls: controls,
      usd_cap: current.usd_cap,
      require_high_confidence: current.require_high_confidence === true
    });
  }

  function commit(body) {
    setStatus("Saving");
    fetch("/v1/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (response) {
      return response.json().then(function (payload) {
        return { ok: response.ok, payload: payload };
      });
    }).then(function (outcome) {
      if (!outcome.ok) {
        setStatus("The file was not changed.");
        return;
      }
      paint(outcome.payload);
      setStatus("Saved. The next run uses these modes.");
      if (typeof window.applyBenchCache === "function") {
        window.applyBenchCache(outcome.payload.preset);
      }
    });
  }

  window.deskPreset = function () {
    return current && current.preset ? current.preset : null;
  };

  fetch("/v1/settings").then(function (response) {
    return response.json();
  }).then(function (data) {
    paint(data);
    if (typeof window.applyBenchCache === "function") {
      window.applyBenchCache(data.preset);
    }
  });
})();
