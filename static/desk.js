(function () {
  const root = document.getElementById("desk");
  let materials = null;

  const INTENTS = [
    { re: /memo|ignore|instruction|jailbreak|\burl\b|follow/, need: ["memo", "secrets", "customers"] },
    { re: /secret|sk-proj|api[ -]?key|\btoken\b/, need: ["secrets"] },
    { re: /customer|dump|\btable\b|pesel|alter|database/, need: ["customers"] }
  ];

  function cell(tag, text) {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
  }

  function table(headers, rows) {
    const node = document.createElement("table");
    const head = document.createElement("thead");
    const titles = document.createElement("tr");
    headers.forEach(function (label) {
      titles.appendChild(cell("th", label));
    });
    head.appendChild(titles);
    const body = document.createElement("tbody");
    rows.forEach(function (row) {
      const line = document.createElement("tr");
      row.forEach(function (value) {
        line.appendChild(cell("td", value));
      });
      body.appendChild(line);
    });
    node.append(head, body);
    return node;
  }

  function card(title, body) {
    const article = document.createElement("article");
    article.className = "card";
    article.append(cell("h3", title), body);
    return article;
  }

  function invoices(numbers) {
    const wrap = document.createElement("div");
    const file = cell("p", numbers.file);
    file.className = "meta";
    const headers = numbers.row.map(function (item) { return item.cell; });
    const values = numbers.row.map(function (item) { return String(item.value); });
    wrap.append(file, table(headers, [values]));
    return wrap;
  }

  function customers(list) {
    const rows = list.map(function (person) {
      const detail = person.plan || person.pesel || "";
      return [person.name, person.account, detail];
    });
    return table(["Name", "Account", "Plan"], rows);
  }

  function memo(company) {
    const wrap = document.createElement("div");
    wrap.appendChild(cell("p", company.documents[0]));
    company.secrets.forEach(function (secret) {
      const line = cell("p", secret);
      line.className = "meta";
      wrap.appendChild(line);
    });
    return wrap;
  }

  function paint(desk) {
    root.replaceChildren(
      card("Invoices", invoices(desk.numbers)),
      card("Customers", customers(desk.company.customers)),
      card("Memo", memo(desk.company))
    );
  }

  function invoiceText(numbers) {
    const cells = numbers.row.map(function (item) {
      return item.cell + "=" + String(item.value);
    });
    return "Invoices file " + numbers.file + ": " + cells.join(" ");
  }

  function customerText(list) {
    const lines = list.map(function (person) {
      const detail = person.plan || person.pesel || "";
      return person.name + "\t" + person.account + "\t" + detail;
    });
    return "Customers:\nName\tAccount\tPlan\n" + lines.join("\n");
  }

  function selected(text) {
    const want = { invoices: true };
    const lower = text.toLowerCase();
    INTENTS.forEach(function (intent) {
      if (!intent.re.test(lower)) return;
      intent.need.forEach(function (name) {
        want[name] = true;
      });
    });
    return want;
  }

  function deskMessages(text) {
    if (!materials) return null;
    const want = selected(text);
    const parts = [invoiceText(materials.numbers)];
    if (want.customers) parts.push(customerText(materials.company.customers));
    if (want.memo) parts.push("Memo: " + materials.company.documents.join("\n"));
    if (want.secrets) parts.push("Secret: " + materials.company.secrets.join("\n"));
    return [
      { role: "system", content: "Desk materials currently open:\n" + parts.join("\n\n") },
      { role: "user", content: text }
    ];
  }

  function read(url) {
    return fetch(url).then(function (response) {
      if (!response.ok) return { error: response.status };
      return response.json().then(function (value) {
        return { value: value };
      });
    });
  }

  window.deskMessages = deskMessages;
  window.deskReady = function () {
    return materials !== null;
  };

  Promise.all([read("/v1/demo/numbers"), read("/assets/company.json")]).then(function (loaded) {
    const numbers = loaded[0];
    const company = loaded[1];
    if (numbers.error || company.error) {
      root.textContent = "The desk fixtures did not load.";
      return;
    }
    materials = { numbers: numbers.value, company: company.value };
    paint(materials);
  });
})();
