(function () {
  let token = 0;

  window.isCodingExample = function (text) {
    const value = text.toLowerCase();
    return value.indexOf("chatbot") !== -1 && value.indexOf("anthropic") !== -1;
  };

  window.playCodingExample = function (root) {
    token += 1;
    const run = token;
    root.hidden = false;
    root.replaceChildren();
    const chain = document.createElement("div");
    chain.className = "chain";
    root.appendChild(chain);

    const steps = [
      step("Ask", "make a simple chatbot menu with anthropic api", "the person"),
      step("Tool", "list_files", "."),
      step("Result", "src/  .env  README.md", "the project"),
      step("Tool", "read_file", ".env")
    ];

    steps.forEach(function (node, index) {
      window.setTimeout(function () {
        if (run !== token) return;
        chain.appendChild(node);
      }, index * 450);
    });

    window.setTimeout(function () {
      if (run !== token) return;
      chain.appendChild(redacted());
    }, steps.length * 450);

    window.setTimeout(function () {
      if (run !== token) return;
      root.appendChild(menu());
    }, steps.length * 450 + 700);
  };

  function step(kind, name, detail) {
    const node = document.createElement("article");
    node.className = "step";
    const label = document.createElement("p");
    label.className = "kind";
    label.textContent = kind;
    const title = document.createElement("h3");
    title.textContent = name;
    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = detail;
    node.append(label, title, meta);
    return node;
  }

  function redacted() {
    const node = document.createElement("article");
    node.className = "step redact";
    const label = document.createElement("p");
    label.className = "kind";
    label.textContent = "Stripped";
    const title = document.createElement("h3");
    title.textContent = "The agent did not see the key";
    const file = document.createElement("pre");
    file.textContent = "ANTHROPIC_APIKEY=";
    const kept = document.createElement("span");
    kept.className = "kept";
    kept.textContent = "[REDACTED]";
    file.appendChild(kept);
    const note = document.createElement("p");
    note.textContent = "read_file ran. The proxy replaced the key before it entered the agent's context. The file's secret was not shown.";
    node.append(label, title, file, note);
    return node;
  }

  function menu() {
    const node = document.createElement("section");
    node.className = "menu";
    const header = document.createElement("header");
    const title = document.createElement("h3");
    title.textContent = "Chat";
    header.appendChild(title);
    const thread = document.createElement("div");
    thread.className = "thread";
    thread.appendChild(bubble("Ask me something.", false));
    const form = document.createElement("form");
    form.className = "composer";
    const input = document.createElement("input");
    input.placeholder = "Message";
    const button = document.createElement("button");
    button.type = "submit";
    button.textContent = "Send";
    form.append(input, button);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const text = input.value.trim();
      if (!text) return;
      thread.appendChild(bubble(text, true));
      thread.appendChild(bubble("Got it. This menu was built without the Anthropic key.", false));
      input.value = "";
    });
    node.append(header, thread, form);
    return node;
  }

  function bubble(text, fromUser) {
    const node = document.createElement("p");
    node.className = fromUser ? "bubble user" : "bubble";
    node.textContent = text;
    return node;
  }
})();
