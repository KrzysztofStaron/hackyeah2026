(function () {
  const policy = document.getElementById("policy-file");
  const signatures = document.getElementById("signature-file");
  const note = document.getElementById("rules-note");
  const posture = document.getElementById("posture");
  let samples = { standard: "", strict: "" };

  function load() {
    return fetch("/v1/catalog").then(function (response) {
      return response.json();
    }).then(function (data) {
      policy.value = data.policy;
      signatures.value = data.signatures;
      samples = data;
    });
  }

  function save(nextPolicy, nextSignatures) {
    return fetch("/v1/catalog", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ policy: nextPolicy, signatures: nextSignatures })
    }).then(function (response) {
      return response.json().then(function (body) {
        return { status: response.status, body: body };
      });
    }).then(function (result) {
      if (result.status === 200) {
        note.textContent = "Saved. The next request uses this copy.";
        return load();
      }
      note.textContent = result.body.error === "signatures.invalid"
        ? "signatures.json did not parse. The last good copy stays."
        : "policy.yaml did not parse. The last good copy stays.";
    }, function () {
      note.textContent = "The proxy did not answer.";
    });
  }

  document.getElementById("save-rules").addEventListener("click", function () {
    save(policy.value, signatures.value);
  });
  document.getElementById("use-standard").addEventListener("click", function () {
    policy.value = samples.standard;
    save(samples.standard, signatures.value);
  });
  document.getElementById("use-strict").addEventListener("click", function () {
    policy.value = samples.strict;
    save(samples.strict, signatures.value);
  });

  function poll() {
    fetch("/v1/report").then(function (response) {
      return response.json();
    }).then(function (data) {
      const controls = data.controls || {};
      const on = Object.keys(controls).filter(function (name) { return controls[name]; }).join(", ");
      const spent = data.agents || {};
      const usd = Object.keys(spent).reduce(function (sum, name) { return sum + Number(spent[name].usd || 0); }, 0);
      posture.replaceChildren();
      [
        ["Blocked", String(data.blocked || 0)],
        ["Stripped", String(data.redacted || 0)],
        ["Spent", "$" + usd.toFixed(4)],
        ["Profile", data.profile || ""],
        ["Email", data.email_action || ""],
        ["On", on || "none"]
      ].forEach(function (pair) {
        const node = document.createElement("div");
        node.className = "metric";
        const value = document.createElement("b");
        value.textContent = pair[1];
        node.append(value, document.createTextNode(pair[0]));
        posture.append(node);
      });
      if (window.fillAgents && data.roster) window.fillAgents(Object.keys(data.roster));
    });
  }

  load();
  poll();
  setInterval(poll, 2000);
})();
