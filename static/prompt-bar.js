(function () {
  const SOURCES = [
    { key: "invoices", name: "Invoices", desc: "Open invoice rows & SQL hints" },
    { key: "customers", name: "Customers", desc: "Customer table from database.sqlite" },
    { key: "memo", name: "Memo", desc: "Poisoned memo on the desk" },
    { key: "secrets", name: "Secrets", desc: "API key in desk materials" }
  ];

  function icon(paths, size) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", String(size || 15));
    svg.setAttribute("height", String(size || 15));
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "1.8");
    svg.setAttribute("aria-hidden", "true");
    paths.forEach(function (d) {
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", d);
      svg.appendChild(path);
    });
    return svg;
  }

  function parseAtToken(draft) {
    const match = /(^|\s)@([\w-]*)$/.exec(draft);
    if (!match) return null;
    return {
      query: match[2].toLowerCase(),
      start: match.index + match[1].length
    };
  }

  function init(options) {
    const mount = options.mount;
    const onSend = options.onSend;
    if (!mount || typeof onSend !== "function") return;

    let draft = "";
    let dismissed = false;
    let plusOpen = false;
    let active = 0;
    let engaged = false;
    let expanded = false;
    let attachKeys = [];
    const root = document.createElement("div");
    root.className = "prompt-bar";
    root.setAttribute("data-promptbar", "");

    const anchor = document.createElement("div");
    anchor.className = "prompt-bar__anchor";

    const menu = document.createElement("div");
    menu.className = "prompt-bar__menu";
    menu.hidden = true;

    const menuHighlight = document.createElement("span");
    menuHighlight.className = "prompt-bar__menu-highlight";
    menuHighlight.setAttribute("aria-hidden", "true");
    menu.appendChild(menuHighlight);

    const menuList = document.createElement("div");
    menuList.className = "prompt-bar__menu-list";
    menu.appendChild(menuList);

    const menuFoot = document.createElement("p");
    menuFoot.className = "prompt-bar__menu-foot meta";
    menu.appendChild(menuFoot);

    const composer = document.createElement("div");
    composer.className = "prompt-bar__composer";

    const chips = document.createElement("div");
    chips.className = "prompt-bar__chips";
    chips.hidden = true;

    const measure = document.createElement("span");
    measure.className = "prompt-bar__measure";
    measure.setAttribute("aria-hidden", "true");

    const controls = document.createElement("div");
    controls.className = "prompt-bar__controls";

    const plus = document.createElement("button");
    plus.type = "button";
    plus.className = "prompt-bar__icon-btn";
    plus.setAttribute("aria-label", "Attach desk materials");
    plus.appendChild(icon(["M12 5v14M5 12h14"], 16));

    const input = document.createElement("textarea");
    input.rows = 1;
    input.className = "prompt-bar__input";
    input.setAttribute("aria-label", "Prompt");
    input.placeholder = "What should the agent try? Type @ to attach desk materials.";

    const model = document.createElement("span");
    model.className = "prompt-bar__model meta";
    model.textContent = "gpt-4o-mini";

    const send = document.createElement("button");
    send.type = "button";
    send.className = "prompt-bar__send";
    send.setAttribute("aria-label", "Send");
    send.disabled = true;
    send.appendChild(icon(["M12 19V5M5 12l7-7 7 7"], 16));

    controls.append(plus, input, model, send);
    composer.append(measure, chips, controls);
    anchor.append(menu, composer);
    root.appendChild(anchor);
    mount.replaceChildren(root);

    const rowRefs = [];

    function token() {
      return dismissed ? null : parseAtToken(draft);
    }

    function menuOpen() {
      return plusOpen || token() !== null;
    }

    function menuQuery() {
      if (plusOpen) return "";
      const t = token();
      return t ? t.query : "";
    }

    function rows() {
      if (!menuOpen()) return [];
      const query = menuQuery();
      return SOURCES.filter(function (row) {
        return row.name.toLowerCase().includes(query) || row.key.includes(query);
      });
    }

    function paintChips() {
      chips.replaceChildren();
      chips.hidden = attachKeys.length === 0;
      attachKeys.forEach(function (key) {
        const source = SOURCES.find(function (row) { return row.key === key; });
        const chip = document.createElement("span");
        chip.className = "prompt-bar__chip";
        chip.textContent = source ? source.name : key;
        const remove = document.createElement("button");
        remove.type = "button";
        remove.setAttribute("aria-label", "Remove " + chip.textContent);
        remove.textContent = "×";
        remove.addEventListener("click", function () {
          attachKeys = attachKeys.filter(function (item) { return item !== key; });
          paintChips();
          syncSend();
        });
        chip.appendChild(remove);
        chips.appendChild(chip);
      });
    }

    function syncSend() {
      const canSend = draft.trim().length > 0 || attachKeys.length > 0;
      send.disabled = !canSend;
    }

    function resizeInput() {
      const wide = draft.indexOf("\n") !== -1
        || measure.offsetWidth + 8 > controls.clientWidth - 120;
      controls.classList.toggle("prompt-bar__controls--wide", wide);
      expanded = wide;
      input.style.height = "0px";
      const next = Math.min(Math.max(input.scrollHeight, 28), 100);
      input.style.height = String(next) + "px";
      input.style.overflowY = input.scrollHeight > 100 ? "auto" : "hidden";
    }

    function closeMenus() {
      plusOpen = false;
      menu.hidden = true;
    }

    function paintMenu() {
      const list = rows();
      if (!menuOpen()) {
        menu.hidden = true;
        return;
      }
      menu.hidden = false;
      menuFoot.textContent = "Attach desk materials to this prompt";
      rowRefs.length = 0;
      menuList.replaceChildren();
      if (!list.length) {
        const empty = document.createElement("p");
        empty.className = "prompt-bar__menu-empty meta";
        empty.textContent = "No matches for \"" + menuQuery() + "\"";
        menuList.appendChild(empty);
        menuHighlight.style.opacity = "0";
        return;
      }
      if (active >= list.length) active = 0;
      list.forEach(function (row, index) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "prompt-bar__menu-row";
        const name = document.createElement("span");
        name.className = "prompt-bar__menu-name";
        name.textContent = row.name;
        const desc = document.createElement("span");
        desc.className = "prompt-bar__menu-desc";
        desc.textContent = row.desc;
        button.append(name, desc);
        button.addEventListener("mouseenter", function () {
          active = index;
          engaged = true;
          moveHighlight();
        });
        button.addEventListener("mousedown", function (event) {
          event.preventDefault();
        });
        button.addEventListener("click", function () {
          pick(row);
        });
        rowRefs[index] = button;
        menuList.appendChild(button);
      });
      moveHighlight();
    }

    function moveHighlight() {
      const target = rowRefs[active];
      if (!target || !engaged) {
        menuHighlight.style.opacity = "0";
        return;
      }
      menuHighlight.style.opacity = "1";
      menuHighlight.style.top = String(target.offsetTop) + "px";
      menuHighlight.style.height = String(target.offsetHeight) + "px";
    }

    function pick(row) {
      const t = token();
      if (attachKeys.indexOf(row.key) === -1) attachKeys.push(row.key);
      paintChips();
      if (t) draft = draft.slice(0, t.start);
      dismissed = false;
      plusOpen = false;
      input.value = draft;
      measure.textContent = draft;
      resizeInput();
      syncSend();
      paintMenu();
      input.focus();
    }

    function submit() {
      const text = draft.trim();
      if (!text && !attachKeys.length) return;
      const payload = text || "Use the attached desk materials.";
      onSend(payload, attachKeys.slice());
      draft = "";
      attachKeys = [];
      input.value = "";
      measure.textContent = "";
      paintChips();
      resizeInput();
      syncSend();
      closeMenus();
    }

    input.addEventListener("input", function () {
      draft = input.value;
      measure.textContent = draft;
      dismissed = false;
      plusOpen = false;
      active = 0;
      engaged = false;
      resizeInput();
      syncSend();
      paintMenu();
    });

    input.addEventListener("keydown", function (event) {
      const list = rows();
      if (menuOpen() && list.length) {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          engaged = true;
          active = (active + (event.key === "ArrowDown" ? 1 : list.length - 1)) % list.length;
          moveHighlight();
          return;
        }
        if ((event.key === "Enter" && !event.shiftKey) || event.key === "Tab") {
          event.preventDefault();
          pick(list[active]);
          return;
        }
      }
      if (event.key === "Escape") {
        dismissed = true;
        closeMenus();
        return;
      }
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        submit();
      }
    });

    plus.addEventListener("click", function () {
      plusOpen = !plusOpen;
      active = 0;
      engaged = false;
      paintMenu();
      input.focus();
    });

    send.addEventListener("click", submit);

    document.addEventListener("pointerdown", function (event) {
      if (!root.contains(event.target)) closeMenus();
    });

    return {
      focus: function () { input.focus(); },
      setSubmitting: function (busy) {
        input.disabled = busy;
        plus.disabled = busy;
        send.disabled = busy || (draft.trim().length === 0 && attachKeys.length === 0);
      },
    };
  }

  window.initDeskPromptBar = init;
})();
