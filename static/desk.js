(function () {
  const ask = document.getElementById("ask");
  const agent = document.getElementById("agent");
  const send = document.getElementById("send");
  const result = document.getElementById("result");

  const reasons = {
    data_secret: "Secret blocked before the model.",
    data_email: "Email blocked.",
    "tool.denied": "Tool is not on this agent.",
    "model.unknown": "Model is not in the policy.",
    budget: "Budget cap reached.",
    "jev.instruction_override": "Jev scored an instruction override.",
    "jev.data_exfiltration": "Jev scored data leaving.",
    "jev.uncertain": "Jev was unsure, so the call stopped.",
    "jev.error": "Jev returned no score, so the call stopped."
  };

  send.addEventListener("click", function () {
    const text = ask.value.trim();
    if (text === "") return;
    send.disabled = true;
    const requestId = String(Date.now());
    fetch("/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Agent-Id": agent.value, "X-Request-Id": requestId },
      body: JSON.stringify({ model: "gpt-4o-mini", messages: [{ role: "user", content: text }] })
    }).then(function (response) {
      return response.json().then(function (payload) {
        return { status: response.status, payload: payload };
      });
    }).then(function (outcome) {
      return fetch("/v1/report").then(function (response) {
        return response.json();
      }).then(function (data) {
        show(outcome, eventFor(data.events, requestId));
        send.disabled = false;
      });
    }, function () {
      send.disabled = false;
      show(null, null);
    });
  });

  function eventFor(events, requestId) {
    const list = events || [];
    for (let index = list.length - 1; index >= 0; index -= 1) {
      if (list[index].request_id === requestId) return list[index];
    }
    return null;
  }

  function show(outcome, event) {
    const status = outcome ? outcome.status : 0;
    const decision = status === 403 ? "block" : status === 200 && event && event.decision === "redact" ? "redact" : status === 200 ? "allow" : "error";
    const code = outcome && outcome.payload && outcome.payload.error ? outcome.payload.error.code : event ? event.check : "";
    const title = decision === "block" ? "Stopped" : decision === "redact" ? "Stripped" : decision === "allow" ? "Allowed" : "No answer";
    const detail = decision === "block" ? (reasons[code] || String(code || "Stopped")) : decision === "redact" ? "A match was replaced with [REDACTED]." : decision === "allow" ? "The checks left this request alone." : "The proxy did not answer.";
    result.hidden = false;
    result.className = "result " + decision;
    const nodes = [el("h2", title), el("p", detail)];
    if (event) nodes.push(el("p", telemetry(event), "meta"));
    const answer = answerText(outcome && outcome.payload);
    if (answer) nodes.push(el("pre", answer));
    const seen = event && event.sanitized;
    if (seen && seen.length) seen.forEach(function (text) { nodes.push(el("pre", text)); });
    result.replaceChildren.apply(result, nodes);
  }

  function telemetry(event) {
    const jev = event.jev ? " Jev " + Object.keys(event.jev).map(function (name) { return name + " " + event.jev[name]; }).join(", ") : "";
    return event.latency_ms + " ms" + (event.jev_latency_ms ? " · Jev " + Math.round(event.jev_latency_ms) + " ms" : "") + " · $" + Number(event.usd || 0).toFixed(6) + jev;
  }

  function answerText(payload) {
    const choices = payload && payload.choices;
    if (!choices || !choices.length) return "";
    const message = choices[0].message;
    return message && typeof message.content === "string" ? message.content : "";
  }

  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = text;
    return node;
  }

  window.fillAgents = function (names) {
    const current = agent.value;
    agent.replaceChildren();
    names.forEach(function (name) {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      agent.append(option);
    });
    if (names.indexOf(current) !== -1) agent.value = current;
    else if (names.indexOf("mira") !== -1) agent.value = "mira";
  };
})();
