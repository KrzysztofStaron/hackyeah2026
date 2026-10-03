(function () {
  const bench = document.getElementById("bench");
  const runButton = document.getElementById("run");
  const score = document.getElementById("bench-score");
  const custom = document.getElementById("custom");
  const customResult = document.getElementById("custom-result");
  runButton.disabled = true;

  let cases = [];
  const finished = [];

  function about(item) {
    const place = item.title.replace(item.source + " ", "");
    if (item.source === "R-Judge") {
      return "R-Judge, EMNLP. A finished agent trace labeled safe or unsafe. This trace is " + place + ".";
    }
    if (item.source === "InjecAgent") {
      return "InjecAgent, ACL. A normal request whose tool result hides a direct-harm attack. Attack type: " + place + ".";
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
    prompt.textContent = item.label + " · " + item.text;
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

  function send(body, requestId) {
    const headers = { "Content-Type": "application/json", "X-Agent-Id": "demo" };
    if (requestId) headers["X-Request-Id"] = requestId;
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

  function kindOf(item, outcome) {
    if (item.label === "safe") return stopped(outcome) ? "fp" : "tn";
    return stopped(outcome) ? "tp" : "fn";
  }

  function kindText(kind, outcome) {
    const code = outcome.payload && outcome.payload.error ? outcome.payload.error.code : outcome.event.check || "";
    const name = kind === "fp" ? "False positive" : kind === "fn" ? "False negative" : kind === "tp" ? "Caught" : "Allowed";
    return name + (code ? " · " + code : "");
  }

  function showScore() {
    const safe = finished.filter(function (item) { return item.label === "safe"; });
    const unsafe = finished.filter(function (item) { return item.label === "unsafe"; });
    const fp = safe.filter(function (item) { return item.kind === "fp"; }).length;
    const fn = unsafe.filter(function (item) { return item.kind === "fn"; }).length;
    const right = finished.filter(function (item) { return item.kind === "tp" || item.kind === "tn"; }).length;
    const total = finished.length ? (100 * right) / finished.length : 0;
    score.textContent = "Score " + total.toFixed(1) + "% after " + String(finished.length) + " of " + String(cases.length) + ". " + String(right) + " right. False positives " + String(fp) + " of " + String(safe.length) + " safe. False negatives " + String(fn) + " of " + String(unsafe.length) + " unsafe.";
  }

  function runOne(item, line, requestId) {
    line.status.textContent = "Running";
    return send(item.body, requestId).then(function (outcome) {
      const kind = kindOf(item, outcome);
      finished.push({ label: item.label, kind: kind });
      line.className = "case " + (kind === "fp" || kind === "fn" ? "block" : "allow");
      line.status.textContent = kindText(kind, outcome);
      showScore();
    }, function () {
      line.className = "case block";
      line.status.textContent = "The proxy did not answer.";
    });
  }

  function runAll() {
    runButton.disabled = true;
    finished.splice(0, finished.length);
    paint();
    score.textContent = "Running 0 of " + String(cases.length) + ".";
    fetch("/v1/demo/reset", { method: "POST" }).then(function () {
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

  document.getElementById("send-custom").addEventListener("click", function () {
    const text = custom.value.trim();
    if (!text) return;
    customResult.hidden = false;
    customResult.className = "result";
    customResult.textContent = "Running";
    send({ model: "gpt-4o-mini", messages: [{ role: "user", content: text }] }).then(function (outcome) {
      const blocked = outcome.status === 403 || outcome.event.decision === "block";
      const code = outcome.payload && outcome.payload.error ? outcome.payload.error.code : outcome.event.check || "";
      customResult.className = "result " + (blocked ? "block" : "allow");
      customResult.textContent = (blocked ? "Blocked" : "Allowed") + (code ? " · " + code : "");
    });
  });

  fetch("/assets/bench.json").then(function (response) {
    return response.json();
  }).then(function (book) {
    cases = (book.cases || []).slice(0, 100);
    paint();
    runButton.disabled = false;
  });

  runButton.addEventListener("click", runAll);
})();
