const team = location.pathname.split("/").filter(Boolean).pop();
const $ = (id) => document.getElementById(id);

const els = {
  conn: $("conn-bar"), session: $("case-session"), timer: $("timer"), score: $("score"),
  teamName: $("team-name"), title: $("round-title"), notice: $("notice"),
  hintCard: $("hint-card"), hintToggle: $("hint-toggle"), notesBody: $("notes-body"),
  hintTitle: $("hint-title"), hintList: $("hint-list"), revealTitle: $("reveal-title"), revealList: $("reveal-list"),
  overlayCodesTitle: $("overlay-codes-title"), overlayCodes: $("overlay-codes"),
  transcript: $("transcript"), chat: $("chat"), chatEmpty: $("chat-empty"),
  sendForm: $("send-form"), message: $("message"), sendBtn: $("send-btn"), sendNote: $("send-note"),
  guessForm: $("guess-form"), code: $("code"), guessBtn: $("guess-btn"), guessNote: $("guess-note"),
  stamp: $("stamp"), overlay: $("overlay"), overlayStamp: $("overlay-stamp"), overlayText: $("overlay-text"),
  hostBtn: $("host-btn"), hostDialog: $("host-dialog"), hostBody: $("host-body"),
  hostNote: $("host-note"), hostClose: $("host-close"),
};

const HOW_ENDED = {
  cracked_all: (s) => `Cracked all ${s.rounds_total} vaults.`,
  more_rounds: () => "More vaults cracked when time ran out.",
  faster_clear: () => "Same number of vaults, but cracked the last one sooner.",
  tiebreaker: () => "Won the tiebreaker.",
  host_award: () => "Awarded by the host.",
};

const REVEAL_HOW = { cracked: "cracked", skipped: "skipped by the host", unsolved: "not cracked" };

function revealText(r, names) {
  const vault = r.vault === null ? "Tiebreaker" : `Vault ${r.vault}`;
  return `${names[r.team]} · ${vault} · ${r.code} (${REVEAL_HOW[r.how]})`;
}

let state = null;
let chatKey = "";
let hostKey = "";
let pending = null;
let sending = false;
let guessing = false;
let hintsOpen = true;
let confirmNew = false;
const nextNames = { a: "", b: "" };
let hostPin = readPin();

function readPin() {
  try { return sessionStorage.getItem("hostPin"); } catch { return null; }
}
function writePin(pin) {
  try { pin ? sessionStorage.setItem("hostPin", pin) : sessionStorage.removeItem("hostPin"); } catch { /* private mode */ }
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const detail = data && typeof data.detail === "string" ? data.detail : "Check what you typed and try again.";
    const err = new Error(res.status >= 500 && !data ? "The game server had a problem. Try again." : detail);
    err.status = res.status;
    throw err;
  }
  return data;
}

function fmt(seconds) {
  const m = Math.floor(seconds / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return `${m}:${s}`;
}

function note(el, text, alert = false) {
  el.textContent = text;
  el.classList.toggle("alert", alert);
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  node.append(...children);
  return node;
}

async function poll() {
  try {
    const s = await api(`/api/state?team=${team}`);
    els.conn.hidden = true;
    render(s);
  } catch {
    els.conn.hidden = false;
  }
}

function titleFor(s) {
  switch (s.phase) {
    case "lobby": return "Waiting for the host to start";
    case "running": return s.round_name;
    case "tie": return "Tie";
    case "tiebreaker": return s.round_name;
    case "tiebreak_over": return "Time is up";
    default: return "Session over";
  }
}

function render(s) {
  const prev = state;
  state = s;
  const names = s.team_names;
  els.session.textContent = `Session ${s.session}`;
  els.teamName.textContent = names[team];
  document.title = `${names[team]} · VaultBot`;
  els.title.textContent = titleFor(s);
  els.timer.textContent = s.seconds_left == null ? "--:--" : fmt(s.seconds_left);
  els.timer.classList.toggle("low", s.seconds_left != null && s.seconds_left <= 60);
  els.score.textContent = `${names.a} ${s.rounds_cleared.a}/${s.rounds_total} · ${names.b} ${s.rounds_cleared.b}/${s.rounds_total}`;
  renderHints(s, prev);
  renderNotice(s);
  renderChat(s);
  renderControls(s);
  renderOverlay(s);
  if (els.hostDialog.open) renderHost(s);
}

function renderHints(s, prev) {
  const count = s.hints.length + s.reveals.length;
  els.hintCard.hidden = count === 0;
  if (count === 0) return;
  const before = prev && prev.session === s.session ? prev.hints.length + prev.reveals.length : count;
  if (els.hintList.children.length !== s.hints.length) {
    els.hintList.replaceChildren(...s.hints.map((h) => el("li", {}, h)));
  }
  if (els.revealList.children.length !== s.reveals.length) {
    els.revealList.replaceChildren(...s.reveals.map((r) => el("li", {}, revealText(r, s.team_names))));
  }
  els.hintTitle.hidden = els.hintList.hidden = s.hints.length === 0;
  els.revealTitle.hidden = els.revealList.hidden = s.reveals.length === 0;
  if (count > before) {
    hintsOpen = true;
    els.hintCard.classList.remove("arrive");
    void els.hintCard.offsetWidth;
    els.hintCard.classList.add("arrive");
  }
  els.notesBody.hidden = !hintsOpen;
  els.hintToggle.setAttribute("aria-expanded", String(hintsOpen));
  const parts = [];
  if (s.hints.length) parts.push(`${s.hints.length} of ${s.hints_total} hints`);
  if (s.reveals.length) parts.push(`${s.reveals.length} ${s.reveals.length === 1 ? "code" : "codes"}`);
  els.hintToggle.textContent = `${parts.join(", ")} (${hintsOpen ? "hide" : "show"})`;
}

function renderNotice(s) {
  const show = s.phase === "running" && s.winner && s.winner !== team;
  els.notice.hidden = !show;
  if (show) {
    els.notice.textContent = `${s.team_names[s.winner]} cracked all ${s.rounds_total} vaults and won. Keep playing until the timer ends to see how far you get.`;
  }
}

function emptyText(s) {
  if (s.phase === "lobby") return "Waiting for the host to start the session.";
  if (s.phase === "running" || s.phase === "tiebreaker") {
    return "No messages yet. Say hello to VaultBot, then try to get the code out of it.";
  }
  return "";
}

function line(m) {
  const what = el("span", { class: "what" });
  if (m.censored) what.append(el("span", { class: "redacted" }, m.text));
  else what.textContent = m.text;
  const cls = m.role + (m.pendingLine ? " pending" : "");
  return el("li", { class: cls }, el("span", { class: "who" }, m.role === "you" ? "YOU:" : "GUARD:"), what);
}

function renderChat(s) {
  const key = `${s.session}|${s.phase}|${s.round_name}|${s.chat.length}|${pending ?? ""}`;
  if (key === chatKey) return;
  chatKey = key;
  const lines = s.chat.map(line);
  if (pending) {
    lines.push(line({ role: "you", text: pending }));
    lines.push(line({ role: "guard", text: "VaultBot is typing...", pendingLine: true }));
  }
  els.chat.replaceChildren(...lines);
  els.chatEmpty.textContent = emptyText(s);
  els.chatEmpty.hidden = lines.length > 0 || !els.chatEmpty.textContent;
  els.transcript.scrollTop = els.transcript.scrollHeight;
}

function renderControls(s) {
  const doneEarly = s.phase === "running" && s.team_done[team];
  const active = (s.phase === "running" || s.phase === "tiebreaker") && !doneEarly;
  els.message.disabled = !active;
  els.sendBtn.disabled = !active || sending || s.busy;
  els.code.disabled = !active;
  const wait = s.cooldown_s || 0;
  els.guessBtn.disabled = !active || guessing || wait > 0;
  els.guessBtn.textContent = wait > 0 ? `Try again in ${wait}s` : "Try this code";
}

function renderOverlay(s) {
  let stamp = "";
  let text = "";
  const other = team === "a" ? "b" : "a";
  if (s.phase === "running" && s.winner === team) {
    stamp = "YOU WIN";
    text = `${s.team_names[team]} cracked all ${s.rounds_total} vaults first. ${s.team_names[other]} keeps playing until the timer ends.`;
  } else if (s.phase === "finished" && s.winner) {
    stamp = s.winner === team ? "YOU WIN" : "SESSION OVER";
    text = `${s.team_names[s.winner]} wins session ${s.session}. ${HOW_ENDED[s.how_ended](s)}`;
  } else if (s.phase === "tie") {
    stamp = "TIE";
    text = "Tie. Waiting for the host to start the tiebreaker.";
  } else if (s.phase === "tiebreak_over") {
    stamp = "TIME";
    text = "Time is up. The host will choose the winner.";
  }
  els.overlay.hidden = !stamp;
  els.overlayStamp.textContent = stamp;
  els.overlayText.textContent = text;
  const unsolved = s.phase === "running" ? [] : s.reveals.filter((r) => r.how === "unsolved");
  els.overlayCodesTitle.hidden = els.overlayCodes.hidden = unsolved.length === 0;
  els.overlayCodes.replaceChildren(...unsolved.map((r) => el("li", {}, revealText(r, s.team_names))));
}

function showStamp(word) {
  els.stamp.replaceChildren(el("span", {}, word));
  els.stamp.hidden = false;
  setTimeout(() => { els.stamp.hidden = true; }, 1600);
}

els.hintToggle.addEventListener("click", () => {
  hintsOpen = !hintsOpen;
  if (state) renderHints(state, state);
});

els.message.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    els.sendForm.requestSubmit();
  }
});

els.sendForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = els.message.value.trim();
  if (!text) { note(els.sendNote, "Write a message first.", true); return; }
  if (sending || !state) return;
  sending = true;
  pending = text;
  note(els.sendNote, "");
  renderChat(state);
  renderControls(state);
  try {
    await api("/api/chat", { method: "POST", body: JSON.stringify({ team, message: text }) });
    els.message.value = "";
    note(els.sendNote, "Pass the keyboard to a teammate.");
  } catch (err) {
    note(els.sendNote, err.message, true);
  } finally {
    sending = false;
    pending = null;
    chatKey = "";
    await poll();
  }
});

els.code.addEventListener("input", () => {
  els.code.value = els.code.value.replace(/\D/g, "").slice(0, 4);
});

els.guessForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const code = els.code.value.trim();
  if (!/^\d{4}$/.test(code)) { note(els.guessNote, "The code is 4 digits.", true); return; }
  guessing = true;
  if (state) renderControls(state);
  try {
    const r = await api("/api/guess", { method: "POST", body: JSON.stringify({ team, code }) });
    if (r.result === "correct") {
      els.code.value = "";
      note(els.guessNote, "Correct. The vault is open.");
      showStamp("CRACKED");
    } else if (r.result === "wrong") {
      note(els.guessNote, `DENIED. That is not the code. Wait ${Math.ceil(r.cooldown_s)} seconds before the next try.`, true);
    } else if (r.result === "cooldown") {
      note(els.guessNote, `Wait ${Math.ceil(r.cooldown_s)} seconds before the next try.`, true);
    } else {
      note(els.guessNote, "The code is 4 digits.", true);
    }
  } catch (err) {
    note(els.guessNote, err.message, true);
  } finally {
    guessing = false;
    await poll();
  }
});

/* Host dialog */

const DONE = {
  start: () => "The timer is running.",
  "next-hint": () => "Hint shown on both screens.",
  skip: (b) => `Round skipped for ${state.team_names[b.team]}.`,
  tiebreaker: () => "Tiebreaker started.",
  award: (b) => `${state.team_names[b.team]} wins session ${state.session}.`,
  "new-session": () => `Session ${state.session} is ready. Press Start when both teams are seated.`,
  rename: () => "Names saved.",
};

async function runHost(action, body = {}) {
  try {
    await api(`/api/host/${action}`, {
      method: "POST",
      headers: { "X-Host-Pin": hostPin || "" },
      body: JSON.stringify(body),
    });
    confirmNew = false;
    if (action === "new-session") { nextNames.a = ""; nextNames.b = ""; }
    await poll();
    note(els.hostNote, DONE[action](body));
  } catch (err) {
    if (err.status === 401) { hostPin = null; writePin(null); }
    note(els.hostNote, err.message, true);
  }
  renderHost(state, true);
}

function hostButton(label, action, body = {}, cls = "") {
  return el("button", { type: "button", class: cls, onclick: () => runHost(action, body) }, label);
}

function nameField(id, label, value, onInput) {
  const input = el("input", { id, maxlength: "24", autocomplete: "off" });
  input.value = value;
  input.addEventListener("input", () => onInput(input.value));
  return [el("label", { for: id }, label), input];
}

function pinForm() {
  const input = el("input", { id: "host-pin", type: "password", inputmode: "numeric", autocomplete: "off" });
  const form = el("form", { class: "host-form" },
    el("label", { for: "host-pin" }, "Host PIN"), input,
    el("button", { type: "submit" }, "Unlock"));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    hostPin = input.value.trim();
    try {
      await api("/api/host/check", { method: "POST", headers: { "X-Host-Pin": hostPin }, body: "{}" });
      writePin(hostPin);
      note(els.hostNote, "");
    } catch (err) {
      hostPin = null;
      note(els.hostNote, err.message, true);
    }
    renderHost(state, true);
  });
  setTimeout(() => input.focus(), 0);
  return form;
}

function section(title, ...children) {
  return el("section", { class: "host-section" }, el("h3", {}, title), ...children);
}

function currentSection(s) {
  const n = s.team_names;
  const parts = [];
  if (s.phase === "lobby") {
    parts.push(hostButton(`Start session ${s.session}`, "start"));
    const names = { a: n.a, b: n.b };
    const form = el("form", { class: "host-form" },
      ...nameField("rename-a", "Name on screen A", n.a, (v) => { names.a = v; }),
      ...nameField("rename-b", "Name on screen B", n.b, (v) => { names.b = v; }),
      el("button", { type: "submit", class: "quiet" }, "Save names"));
    form.addEventListener("submit", (e) => { e.preventDefault(); runHost("rename", names); });
    parts.push(form);
  } else if (s.phase === "running") {
    parts.push(hostButton(`Show the next hint (${s.hints.length} of ${s.hints_total} showing)`, "next-hint"));
    for (const t of ["a", "b"]) {
      if (!s.team_done[t]) parts.push(hostButton(`Skip this round for ${n[t]}`, "skip", { team: t }, "quiet"));
    }
  } else if (s.phase === "tie") {
    parts.push(
      hostButton("Start the tiebreaker", "tiebreaker"),
      hostButton(`Award the win to ${n.a}`, "award", { team: "a" }, "quiet"),
      hostButton(`Award the win to ${n.b}`, "award", { team: "b" }, "quiet"),
    );
  } else if (s.phase === "tiebreaker") {
    parts.push(el("p", {}, "Tiebreaker running. The first correct code wins."));
  } else if (s.phase === "tiebreak_over") {
    parts.push(
      el("p", {}, `Wrong guesses in the tiebreaker: ${n.a} ${s.tiebreak_wrong.a}, ${n.b} ${s.tiebreak_wrong.b}. Fewer wrong guesses wins.`),
      hostButton(`Award the win to ${n.a}`, "award", { team: "a" }),
      hostButton(`Award the win to ${n.b}`, "award", { team: "b" }),
    );
  } else if (s.phase === "finished") {
    parts.push(el("p", {}, s.winner ? `${n[s.winner]} won session ${s.session}. It is saved on the results page.` : `Session ${s.session} ended.`));
  }
  return section(`Session ${s.session}`, ...parts);
}

function nextSection(s) {
  const stillPlaying = !["lobby", "finished"].includes(s.phase);
  const form = el("form", { class: "host-form" },
    ...nameField("next-a", "Next team on screen A", nextNames.a, (v) => { nextNames.a = v; }),
    ...nameField("next-b", "Next team on screen B", nextNames.b, (v) => { nextNames.b = v; }));
  if (stillPlaying) {
    form.append(el("p", { class: "note alert" }, `Session ${s.session} is still running. It will be saved as stopped early.`));
  }
  const label = stillPlaying && confirmNew
    ? `Yes, stop session ${s.session} and start session ${s.session + 1}`
    : `Save session ${s.session} and start session ${s.session + 1}`;
  form.append(el("button", { type: "submit", class: stillPlaying && confirmNew ? "danger" : "" }, label));
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!nextNames.a.trim() || !nextNames.b.trim()) {
      note(els.hostNote, "Type both team names first.", true);
      return;
    }
    if (stillPlaying && !confirmNew) {
      confirmNew = true;
      renderHost(state, true);
      return;
    }
    runHost("new-session", { a: nextNames.a.trim(), b: nextNames.b.trim() });
  });
  return section("New session", form);
}

function renderHost(s, force = false) {
  if (!s) return;
  const key = `${s.session}|${s.phase}|${s.hints.length}|${s.team_done.a}|${s.team_done.b}|${hostPin ? 1 : 0}|${confirmNew}`;
  if (!force && key === hostKey) return;
  hostKey = key;
  if (!hostPin) { els.hostBody.replaceChildren(pinForm()); return; }
  const parts = [currentSection(s)];
  if (s.phase !== "lobby") parts.push(nextSection(s));
  els.hostBody.replaceChildren(...parts);
}

els.hostBtn.addEventListener("click", () => {
  confirmNew = false;
  note(els.hostNote, "");
  renderHost(state, true);
  els.hostDialog.showModal();
});
els.hostClose.addEventListener("click", () => els.hostDialog.close());

if (!["a", "b"].includes(team)) {
  els.title.textContent = "This page does not exist. Open /team/a or /team/b.";
} else {
  poll();
  setInterval(poll, 1000);
}
