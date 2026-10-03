(function () {
  const prompt = document.getElementById("prompt");
  const agent = document.getElementById("agent");
  const send = document.getElementById("send");
  const result = document.getElementById("result");
  let tools = null;

  const presets = {
    safe: { text: "What is 2 + 2? Reply with only the number.", tools: null },
    secret: { text: "The key is sk-proj-abcdefghijklmnopqrstuv", tools: null },
    email: {
      text: "Write a fictional email address for Ada at example.com. Put the at-sign in the address. Reply with only the address.",
      tools: null
    },
    tool: {
      text: "Run a shell command.",
      tools: [{ type: "function", function: { name: "shell" } }]
    },
    coding: { text: "make a simple chatbot menu with anthropic api", tools: null }
  };

  const reasons = {
    data_secret: "A secret key was in the request. The model was not called.",
    data_email: "An email address stopped the request.",
    "tool.denied": "That function is not on this agent's list.",
    "agent.unknown": "This agent is not in the policy.",
    "agent.missing": "The request had no agent id.",
    "model.unknown": "This model is not in the policy.",
    "signatures.ignore_previous": "The text tried to override the instructions.",
    "signatures.exec": "The arguments tried to run a command.",
    "signatures.pickle": "The arguments tried to load a pickle.",
    "signatures.model_host": "The arguments named a host that is not trusted.",
    "signatures.ssrf": "That address is metadata or the local machine.",
    "signatures.export_dump": "The call tried to move the customer book out.",
    "signatures.path_escape": "The path leaves the workspace.",
    "signatures.sql_danger": "That statement is not a plain read.",
    "signatures.command": "That command is destructive.",
    budget: "This agent is already at its dollar cap.",
    "jev.instruction_override": "The AI check scored this as an attempt to override the instructions.",
    "jev.data_exfiltration": "The AI check scored this as an attempt to move private data out.",
    "jev.uncertain": "The AI check was unsure, so the request stopped.",
    "jev.error": "The AI check did not return a score, so the request stopped."
  };

  document.querySelectorAll("[data-preset]").forEach(function (button) {
    button.addEventListener("click", function () {
      const preset = presets[button.getAttribute("data-preset")];
      prompt.value = preset.text;
      tools = preset.tools;
    });
  });

  send.addEventListener("click", function () {
    const coding = document.getElementById("coding");
    if (window.isCodingExample(prompt.value)) {
      result.hidden = true;
      window.playCodingExample(coding);
      return;
    }
    coding.hidden = true;
    send.disabled = true;
    const body = { model: "gpt-4o-mini", messages: [{ role: "user", content: prompt.value }] };
    if (tools) body.tools = tools;
    fetch("/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Agent-Id": agent.value },
      body: JSON.stringify(body)
    }).then(function (response) {
      return response.json().then(function (payload) {
        return { status: response.status, payload: payload };
      });
    }).then(function (outcome) {
      return fetch("/v1/report").then(function (response) {
        return response.json();
      }).then(function (data) {
        render(data);
        showResult(outcome, data);
        send.disabled = false;
      });
    }, function () {
      send.disabled = false;
      showFailure();
    });
  });

  function showFailure() {
    result.hidden = false;
    result.className = "result block";
    result.replaceChildren(heading("No answer"), paragraph("The proxy did not answer."));
  }

  function showResult(outcome, data) {
    const events = data.events || [];
    const event = events.length ? events[events.length - 1] : {};
    const decision = outcome.status === 403 ? "block" : String(event.decision || "allow");
    const code = outcome.payload && outcome.payload.error ? outcome.payload.error.code : event.check;
    result.hidden = false;
    result.className = "result " + (decision === "redact" ? "redact" : decision === "block" ? "block" : "allow");
    const title = decision === "block" ? "Stopped" : decision === "redact" ? "Stripped" : "Allowed";
    const reason = decision === "redact"
      ? "A match was replaced with [REDACTED] before it stayed in context."
      : decision === "block"
        ? (reasons[code] || String(code || "Stopped"))
        : "The checks left this request alone.";
    const nodes = [heading(title), paragraph(reason), paragraph(telemetry(event), "meta")];
    const answer = answerText(outcome.payload);
    if (answer) nodes.push(blockText(answer));
    result.replaceChildren.apply(result, nodes);
  }

  function heading(text) {
    const node = document.createElement("h2");
    node.textContent = text;
    return node;
  }

  function paragraph(text, className) {
    const node = document.createElement("p");
    if (className) node.className = className;
    node.textContent = text;
    return node;
  }

  function blockText(text) {
    const node = document.createElement("pre");
    node.textContent = text;
    return node;
  }

  function answerText(payload) {
    if (!payload || !payload.choices || !payload.choices[0] || !payload.choices[0].message) return "";
    return payload.choices[0].message.content || "";
  }

  function telemetry(event) {
    const parts = [];
    if (event.latency_ms != null) parts.push(String(event.latency_ms) + " ms");
    if (event.jev_latency_ms != null) parts.push("Jev " + String(Math.round(event.jev_latency_ms)) + " ms");
    if (event.usd != null) parts.push("$" + String(event.usd));
    if (event.jev) {
      Object.keys(event.jev).forEach(function (name) {
        parts.push(name + " " + String(event.jev[name]));
      });
    }
    return parts.join(" · ");
  }

  function render(data) {
    const loaded = document.getElementById("loaded");
    const email = data.email_action || "off";
    const secret = data.secret_action || "off";
    const thresholds = data.jev_thresholds || {};
    loaded.textContent = "Profile " + data.profile + " · loaded " + data.loaded_at + " · email " + email + " · secret " + secret + " · Jev " + (thresholds.instruction_override || "");

    const metrics = document.getElementById("metrics");
    metrics.replaceChildren(
      metric("Blocked", data.blocked),
      metric("Stripped", data.redacted),
      metric("Agents", Object.keys(data.agents || {}).length)
    );

    const policy = document.getElementById("policy");
    policy.replaceChildren();
    const roster = data.roster || {};
    Object.keys(roster).forEach(function (name) {
      const card = document.createElement("article");
      card.className = "card";
      const title = document.createElement("h3");
      title.textContent = name;
      const spend = data.agents && data.agents[name] ? data.agents[name].usd : 0;
      const line = document.createElement("p");
      line.textContent = "Cap $" + roster[name].usd_cap + " · spent $" + spend + " · " + roster[name].tools.join(", ");
      card.append(title, line);
      policy.appendChild(card);
    });

    fillAgents(Object.keys(roster));

    const events = document.getElementById("events");
    events.replaceChildren();
    (data.events || []).forEach(function (event) {
      const row = document.createElement("tr");
      [event.ts, event.agent, event.decision, event.check, event.latency_ms, event.jev_latency_ms, event.usd].forEach(function (value) {
        const cell = document.createElement("td");
        cell.textContent = value == null ? "" : String(value);
        row.appendChild(cell);
      });
      events.appendChild(row);
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

  function fillAgents(names) {
    const current = agent.value;
    if (!names.length) names = ["demo"];
    agent.replaceChildren();
    names.forEach(function (name) {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      agent.appendChild(option);
    });
    if (names.indexOf(current) !== -1) agent.value = current;
  }

  function load() {
    fetch("/v1/report").then(function (response) {
      return response.json();
    }).then(render);
  }

  load();
  setInterval(load, 2000);
})();
