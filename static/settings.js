(function () {
  const table = document.getElementById("controls");
  const presets = document.getElementById("presets");
  const status = document.getElementById("settings-status");
  const modes = ["disabled", "redact", "strict"];
  let current = null;

  function paintPresets(data) {
    presets.replaceChildren();
    data.presets.forEach(function (preset) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = preset.label;
      button.setAttribute("aria-pressed", data.preset === preset.id ? "true" : "false");
      button.addEventListener("click", function () {
        commit({ preset: preset.id });
      });
      presets.appendChild(button);
    });
  }

  function paint(data) {
    current = data;
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
    budgetName.textContent = "Budget";
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
    paintPresets(data);
  }

  function save() {
    const controls = {};
    current.controls.forEach(function (item) {
      controls[item.id] = item.mode;
    });
    commit({ controls: controls, usd_cap: current.usd_cap });
  }

  function commit(body) {
    status.textContent = "Saving";
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
        status.textContent = "The file was not changed.";
        return;
      }
      paint(outcome.payload);
      status.textContent = "Saved. The next run uses these modes.";
    });
  }

  fetch("/v1/settings").then(function (response) {
    return response.json();
  }).then(paint);
})();
