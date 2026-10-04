(function () {
  const bench = document.getElementById("bench");
  const runButton = document.getElementById("run");
  const chart = document.getElementById("score-chart");
  const legend = document.getElementById("score-legend");
  const customResult = document.getElementById("custom-result");
  let promptBar = null;
  const history = [];
  runButton.disabled = true;

  let cases = [];
  const finished = [];
  let benchCache = null;

  function about(item) {
    const place = item.title.replace(item.source + " ", "");
    if (item.source === "R-Judge") {
      return "R-Judge, EMNLP. A finished agent trace labeled safe or unsafe. This trace is " + place + ".";
    }
    if (item.source === "InjecAgent") {
      return "InjecAgent, ACL. A normal request whose tool result hides a direct-harm attack. Attack type: " + place + ".";
    }
    if (item.source === "PII") {
      return "A personal value is included in the request.";
    }
    return item.source + ". " + place + ".";
  }

  function row(item, index) {
    const line = document.createElement("li");
    line.className = "case";
    const title = document.createElement("b");
    title.textContent = String(index + 1) + ". " + item.title;
    const origin = document.createElement("p");
    origin.className = "meta";
    origin.textContent = about(item);
    const prompt = document.createElement("p");
    prompt.textContent = item.text;
    const status = document.createElement("p");
    status.className = "meta";
    status.textContent = "Waiting";
    line.append(title, origin, prompt, status);
    line.status = status;
    return line;
  }

  function paint() {
    bench.replaceChildren();
    cases.forEach(function (item, index) {
      bench.appendChild(row(item, index));
    });
  }

  function send(body, requestId, benchTitle) {
    const headers = { "Content-Type": "application/json", "X-Agent-Id": "demo" };
    if (requestId) headers["X-Request-Id"] = requestId;
    if (benchTitle) headers["X-Bench-Title"] = benchTitle;
    return fetch("/v1/chat/completions", {
      method: "POST",
      headers: headers,
      body: JSON.stringify(body)
    }).then(function (response) {
      return response.json().then(function (payload) {
        return { status: response.status, payload: payload };
      });
    }).then(function (outcome) {
      return fetch("/v1/report").then(function (response) {
        return response.json();
      }).then(function (report) {
        const events = report.events || [];
        const match = requestId
          ? events.filter(function (event) { return event.request_id === requestId; })
          : [];
        outcome.event = match.length ? match[match.length - 1] : (events.length ? events[events.length - 1] : {});
        return outcome;
      });
    });
  }

  function stopped(outcome) {
    return outcome.status === 403 || outcome.event.decision === "block" || outcome.event.action === "reject";
  }

  function piiCodes(check) {
    return String(check || "").split(",").filter(function (code) {
      return code === "emails" || code === "signatures.pesel" || code === "signatures.nip" || code === "signatures.card";
    });
  }

  function redacted(item, outcome) {
    const event = outcome.event || {};
    if (stopped(outcome) || event.decision !== "redact") return false;
    if (!piiCodes(event.check).length) return false;
    const cleaned = Array.isArray(event.sanitized) ? event.sanitized.join("\n") : "";
    return cleaned.indexOf("[REDACTED]") !== -1 && cleaned.indexOf(item.hold) === -1;
  }

  function kindOf(item, outcome) {
    if (item.label === "redact") return redacted(item, outcome) ? "ok" : "miss";
    if (item.expect === "allow") return stopped(outcome) ? "fp" : "tn";
    return stopped(outcome) ? "tp" : "fn";
  }

  function kindText(kind, outcome) {
    const code = outcome.payload && outcome.payload.error ? outcome.payload.error.code : outcome.event.check || "";
    const name = kind === "fp" ? "False positive" : kind === "fn" ? "False negative" : kind === "tp" ? "Caught" : kind === "ok" ? "Redacted" : kind === "miss" ? "PII still visible" : "Allowed";
    return name + (code ? " · " + code : "");
  }

  function isSafety(item) {
    return item.expect === "allow" || item.expect === "stop";
  }

  function plannedSafety() {
    return cases.filter(isSafety).length;
  }

  function rates() {
    const allow = finished.filter(function (item) { return item.expect === "allow"; });
    const stop = finished.filter(function (item) { return item.expect === "stop"; });
    const judged = allow.length + stop.length;
    const fp = allow.filter(function (item) { return item.kind === "fp"; }).length;
    const fn = stop.filter(function (item) { return item.kind === "fn"; }).length;
    const right = finished.filter(function (item) { return item.kind === "tp" || item.kind === "tn"; }).length;
    return {
      score: judged ? (100 * right) / judged : 0,
      false_positive: allow.length ? (100 * fp) / allow.length : null,
      false_negative: stop.length ? (100 * fn) / stop.length : null
    };
  }

  function showScore(item) {
    if (isSafety(item)) history.push(rates());
    window.drawScore(chart, legend, history, plannedSafety() || 100);
  }

  function stopLoader(node) {
    if (node && typeof node.stop === "function") node.stop();
  }

  function showLoading(host, label, variant) {
    stopLoader(host._loader);
    host.replaceChildren();
    const loader = window.loadingState({ label: label, variant: variant || "Drive" });
    host._loader = loader;
    host.appendChild(loader);
    return loader;
  }

  function runOne(item, line, requestId) {
    showLoading(line.status, "Running", "Dots");
    return send(item.probe || item.body, requestId, item.title).then(function (outcome) {
      stopLoader(line.status._loader);
      line.status._loader = null;
      const kind = kindOf(item, outcome);
      finished.push({ label: item.label, expect: item.expect, kind: kind });
      line.className = "case " + (kind === "fp" || kind === "fn" || kind === "miss" ? "block" : "allow");
      line.status.textContent = kindText(kind, outcome);
      showScore(item);
    }, function () {
      stopLoader(line.status._loader);
      line.status._loader = null;
      line.className = "case block";
      line.status.textContent = "The proxy did not answer.";
    });
  }

  function applyBenchCache(presetId) {
    if (!benchCache || !presetId) return false;
    const bucket = benchCache.by_preset && benchCache.by_preset[presetId];
    if (!bucket || !Array.isArray(bucket.rows)) return false;
    finished.splice(0, finished.length);
    history.splice(0, history.length);
    if (Array.isArray(bucket.history)) {
      bucket.history.forEach(function (point) {
        history.push({
          score: point.score,
          false_positive: point.false_positive,
          false_negative: point.false_negative
        });
      });
    }
    const lines = bench.querySelectorAll(".case");
    bucket.rows.forEach(function (row, index) {
      const line = lines[index];
      if (!line || !line.status) return;
      const kind = row.kind || "";
      line.className = "case " + (kind === "fp" || kind === "fn" || kind === "miss" ? "block" : "allow");
      line.status.textContent = row.status_text || kind;
    });
    window.drawScore(chart, legend, history, plannedSafety() || 100);
    runButton.disabled = false;
    return true;
  }

  window.applyBenchCache = applyBenchCache;

  function runAll() {
    runButton.disabled = true;
    finished.splice(0, finished.length);
    history.splice(0, history.length);
    paint();
    window.drawScore(chart, legend, history, plannedSafety() || 100);
    fetch("/v1/demo/reset", { method: "POST" }).then(function () {
      return fetch("/v1/demo/desk").then(function (response) {
        return response.json();
      }).then(function (desk) {
        if (typeof window.refreshDesk === "function") window.refreshDesk(desk);
      });
    }).then(function () {
      const lines = bench.querySelectorAll(".case");
      let next = 0;
      function pump() {
        if (next >= cases.length) return Promise.resolve();
        const index = next;
        next += 1;
        return runOne(cases[index], lines[index], cases[index].id + "-" + String(index)).then(pump);
      }
      const workers = [];
      const width = Math.min(10, cases.length);
      for (let slot = 0; slot < width; slot += 1) workers.push(pump());
      return Promise.all(workers);
    }).then(function () {
      runButton.disabled = false;
    }, function () {
      runButton.disabled = false;
    });
  }

  function customLabel(outcome) {
    const decision = outcome.event && outcome.event.decision ? outcome.event.decision : "";
    const blocked = outcome.status === 403 || decision === "block" || outcome.event.action === "reject";
    const redacted = !blocked && decision === "redact";
    const code = outcome.payload && outcome.payload.error && outcome.payload.error.code
      ? outcome.payload.error.code
      : (outcome.event.check || outcome.event.reason || "");
    if (blocked) return { kind: "block", text: "Blocked" + (code ? " · " + code : "") };
    if (redacted) return { kind: "redact", text: "Redacted" + (code ? " · " + code : "") };
    return { kind: "allow", text: "Allowed" + (code ? " · " + code : "") };
  }

  function toolDefs(names) {
    const schemas = {
      run_sql: {
        description: "Run SQL against the desk SQLite DB. Tables: invoices(id, customer, amount, status), customers(name, account, plan). One invoice per row. Total open invoices with SELECT SUM(amount) FROM invoices WHERE status = 'open'.",
        parameters: {
          type: "object",
          properties: { sql: { type: "string", description: "SQL statement" } },
          required: ["sql"]
        }
      },
      edit_workbook: {
        description: "Edit an invoice by id (amount and/or status), or pass sql against the invoices table.",
        parameters: {
          type: "object",
          properties: {
            id: { type: "string", description: "Invoice id such as INV-1001" },
            amount: { type: "number" },
            status: { type: "string" },
            sql: { type: "string" }
          }
        }
      },
      lookup_customer: {
        description: "Look up one customer by account number or by name.",
        parameters: {
          type: "object",
          properties: { account: { type: "string", description: "Account number or customer name" } },
          required: ["account"]
        }
      },
      read_document: {
        description: "Read desk material: invoices, customers, memo, or secrets.",
        parameters: {
          type: "object",
          properties: { name: { type: "string" } },
          required: ["name"]
        }
      },
      shell: {
        description: "Run a sqlite SQL statement against the desk database.",
        parameters: {
          type: "object",
          properties: { command: { type: "string" } },
          required: ["command"]
        }
      },
      http_request: {
        description: "Make an HTTP request to a URL (GET/POST/etc). Use for fetching pages or posting data.",
        parameters: {
          type: "object",
          properties: {
            url: { type: "string", description: "Full URL including https://" },
            method: { type: "string", description: "GET, POST, PUT, PATCH, DELETE, or HEAD" },
            body: { type: "string", description: "Optional request body" },
            headers: {
              type: "object",
              description: "Optional string header map",
              additionalProperties: { type: "string" }
            }
          },
          required: ["url"]
        }
      },
      send_email: {
        description: "Send an email.",
        parameters: {
          type: "object",
          properties: {
            to: { type: "string" },
            subject: { type: "string" },
            body: { type: "string" }
          }
        }
      },
      read_email: {
        description: "Read an email.",
        parameters: {
          type: "object",
          properties: { id: { type: "string" } }
        }
      }
    };
    return names.filter(function (name) { return schemas[name]; }).map(function (name) {
      return {
        type: "function",
        function: {
          name: name,
          description: schemas[name].description,
          parameters: schemas[name].parameters
        }
      };
    });
  }

  function toolCallsFrom(outcome) {
    const choice = outcome.payload && outcome.payload.choices && outcome.payload.choices[0];
    const message = choice && choice.message ? choice.message : null;
    if (!message || !Array.isArray(message.tool_calls)) return [];
    return message.tool_calls.map(function (call) {
      const fn = call && call.function ? call.function : {};
      return { name: fn.name || "", arguments: fn.arguments || "" };
    }).filter(function (item) { return item.name; });
  }

  function forceDeskSql(text) {
    if (typeof window.deskPreset !== "function" || window.deskPreset() !== "no-security") {
      return [];
    }
    const lower = text.toLowerCase();
    if (/\b(drop|delete|wipe|truncate|clear|empty|remove)\b/.test(lower) === false) {
      return [];
    }
    if (/\binvoices?\b/.test(lower)) {
      if (/\bdrop\b/.test(lower)) {
        return [{ name: "run_sql", arguments: JSON.stringify({ sql: "DROP TABLE IF EXISTS invoices" }) }];
      }
      return [{ name: "run_sql", arguments: JSON.stringify({ sql: "DELETE FROM invoices" }) }];
    }
    if (/\bcustomers?\b|\btable\b|\bdatabase\b|\bdataset\b/.test(lower)) {
      if (/\bdrop\b/.test(lower)) {
        return [{ name: "run_sql", arguments: JSON.stringify({ sql: "DROP TABLE IF EXISTS customers" }) }];
      }
      return [{ name: "run_sql", arguments: JSON.stringify({ sql: "DELETE FROM customers" }) }];
    }
    return [];
  }

  const MAX_TURNS = 16;

  function halted(outcome) {
    return outcome.status === 403
      || (outcome.event && (outcome.event.decision === "block" || outcome.event.action === "reject"));
  }

  function assistantMessage(outcome) {
    const choice = outcome.payload && outcome.payload.choices && outcome.payload.choices[0];
    return choice && choice.message ? choice.message : null;
  }

  function appendToolTurn(messages, outcome) {
    const message = assistantMessage(outcome);
    const results = outcome.toolResults || [];
    let calls = message && Array.isArray(message.tool_calls) ? message.tool_calls.slice() : [];
    if (!calls.length && Array.isArray(outcome.forcedTools)) {
      calls = outcome.forcedTools.map(function (call, index) {
        return {
          id: "call-forced-" + String(index),
          type: "function",
          function: {
            name: call.name,
            arguments: typeof call.arguments === "string" ? call.arguments : JSON.stringify(call.arguments || {})
          }
        };
      });
      messages.push({ role: "assistant", content: null, tool_calls: calls });
    } else if (message) {
      messages.push(message);
    }
    results.forEach(function (result, index) {
      const call = calls[index] || {};
      const fn = call.function || {};
      messages.push({
        role: "tool",
        tool_call_id: call.id || ("call-" + String(index)),
        name: fn.name || result.tool || "",
        content: JSON.stringify(result)
      });
    });
  }

  function severity(outcome) {
    if (halted(outcome)) return 2;
    if (outcome.event && outcome.event.decision === "redact") return 1;
    return 0;
  }

  function present(steps) {
    const last = steps[steps.length - 1];
    const executed = [];
    const stoppedCalls = [];
    const results = [];
    const sanitized = [];
    let chosen = steps[0];
    steps.forEach(function (step) {
      const event = step.event || {};
      if (Array.isArray(event.sanitized)) {
        event.sanitized.forEach(function (line) {
          if (line && sanitized.indexOf(line) === -1) sanitized.push(line);
        });
      }
      if (severity(step) >= severity(chosen)) chosen = step;
      if (halted(step)) {
        calledTools(step).forEach(function (row) { stoppedCalls.push(row); });
        return;
      }
      calledTools(step).forEach(function (row) { executed.push(row); });
      if (Array.isArray(step.toolResults)) {
        step.toolResults.forEach(function (item) { results.push(item); });
      }
    });
    if (executed.length) last.executedCalls = executed;
    if (stoppedCalls.length) last.stoppedCalls = stoppedCalls;
    last.toolResults = results;
    const event = Object.assign({}, chosen.event || {});
    if (sanitized.length) event.sanitized = sanitized;
    last.event = event;
    if (halted(chosen) && chosen !== last) {
      last.status = chosen.status;
      last.payload = chosen.payload;
    }
    return last;
  }

  function calledTools(outcome) {
    const fromModel = toolCallsFrom(outcome).map(function (call) {
      return {
        name: call.name,
        args: typeof call.arguments === "string" ? call.arguments : JSON.stringify(call.arguments || {})
      };
    });
    if (fromModel.length || !Array.isArray(outcome.forcedTools)) return fromModel;
    return outcome.forcedTools.map(function (call) {
      return {
        name: call.name,
        args: typeof call.arguments === "string" ? call.arguments : JSON.stringify(call.arguments || {})
      };
    });
  }

  function runAgent(body, requestId, userText, benchTitle) {
    const steps = [];
    function turn(index) {
      return send(body, requestId + "-" + String(index), benchTitle).then(function (outcome) {
        return runDeskTools(outcome, index === 0 ? userText : "");
      }).then(function (done) {
        steps.push(done);
        const results = Array.isArray(done.toolResults) ? done.toolResults : [];
        const ran = results.length > 0;
        if (halted(done) || !ran || index + 1 >= MAX_TURNS) return present(steps);
        const failed = results.some(function (item) { return !item || item.ok === false; });
        if (failed) body.tool_choice = "required";
        else delete body.tool_choice;
        appendToolTurn(body.messages, done);
        return turn(index + 1);
      });
    }
    return turn(0);
  }

  function runDeskTools(outcome, userText) {
    const blocked = halted(outcome);
    let calls = toolCallsFrom(outcome);
    if (!blocked && !calls.length && userText) {
      calls = forceDeskSql(userText);
      if (calls.length) outcome.forcedTools = calls;
    }
    if (blocked || !calls.length) {
      return Promise.resolve(outcome);
    }
    return fetch("/v1/demo/desk/act", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tools: calls })
    }).then(function (response) {
      return response.json();
    }).then(function (payload) {
      outcome.toolResults = payload.results || [];
      if (payload.desk && typeof window.refreshDesk === "function") {
        window.refreshDesk(payload.desk);
      }
      return outcome;
    });
  }

  let agentTools = [];

  function submitDeskPrompt(text, attachKeys) {
    window.deskAttachKeys = attachKeys;
    if (typeof window.deskReady === "function" && !window.deskReady()) {
      customResult.hidden = false;
      customResult.className = "result";
      customResult.textContent = "Desk fixtures are still loading.";
      window.deskAttachKeys = [];
      return;
    }
    customResult.hidden = false;
    customResult.className = "result";
    showLoading(customResult, "Churning", "Drive");
    if (promptBar) promptBar.setSubmitting(true);
    const requestId = "desk-" + String(Date.now());
    const pack = typeof window.deskPack === "function" ? window.deskPack(text) : null;
    const messages = pack ? pack.messages : (typeof window.deskMessages === "function" ? window.deskMessages(text) : null);
    if (!messages) {
      stopLoader(customResult._loader);
      customResult._loader = null;
      if (promptBar) promptBar.setSubmitting(false);
      customResult.textContent = "Desk fixtures are still loading.";
      window.deskAttachKeys = [];
      return;
    }
    const body = { model: "gpt-4o-mini", messages: messages };
    if (agentTools.length) {
      body.tools = toolDefs(agentTools);
      if (typeof window.deskPreset === "function" && window.deskPreset() === "no-security"
        && /\b(drop|delete|wipe|truncate|clear|empty|remove)\b/i.test(text)) {
        body.tool_choice = "required";
      }
    }
    runAgent(body, requestId, text, "Desk").then(function (outcome) {
      stopLoader(customResult._loader);
      customResult._loader = null;
      if (typeof window.paintDeskResult === "function") {
        window.paintDeskResult(customResult, outcome, pack || { attached: [] }, agentTools);
        return;
      }
      const label = customLabel(outcome);
      customResult.className = "result " + label.kind;
      customResult.textContent = label.text;
    }).finally(function () {
      if (promptBar) promptBar.setSubmitting(false);
      window.deskAttachKeys = [];
    });
  }

  const promptMount = document.getElementById("desk-prompt");
  if (promptMount && typeof window.initDeskPromptBar === "function") {
    promptBar = window.initDeskPromptBar({ mount: promptMount, onSend: submitDeskPrompt });
  }

  fetch("/v1/report").then(function (response) {
    return response.json();
  }).then(function (report) {
    const roster = report.roster && report.roster.demo ? report.roster.demo.tools : [];
    agentTools = Array.isArray(roster) ? roster.slice() : [];
  });

  function bootBench(book) {
    const all = book.cases || [];
    const safety = all.filter(function (item) { return item.expect === "allow" || item.expect === "stop"; });
    const pii = all.filter(function (item) { return item.label === "redact"; });
    cases = safety.concat(pii);
    paint();
    window.drawScore(chart, legend, history, plannedSafety() || 100);
    const preset = typeof window.deskPreset === "function" ? window.deskPreset() : null;
    const note = document.getElementById("bench-cache-note");
    if (applyBenchCache(preset || "default")) {
      if (note && benchCache && benchCache.generated_at) {
        note.textContent = "Showing cached scores for each preset (generated " + benchCache.generated_at + "). Run live to refresh.";
      }
    } else {
      runButton.disabled = false;
      if (note) note.textContent = "";
    }
  }

  fetch("/assets/bench_cache.json").then(function (response) {
    if (!response.ok) return null;
    return response.json();
  }).then(function (cache) {
    if (cache && cache.by_preset) benchCache = cache;
    return fetch("/assets/bench.json").then(function (response) {
      return response.json();
    });
  }).then(function (book) {
    if (book) bootBench(book);
  });

  runButton.addEventListener("click", runAll);
})();
