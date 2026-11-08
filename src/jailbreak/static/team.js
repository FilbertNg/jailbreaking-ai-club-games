const team = location.pathname.split("/").filter(Boolean).pop();
const other = team === "a" ? "b" : "a";
const $ = (id) => document.getElementById(id);

const els = {
  conn: $("conn-bar"), session: $("case-session"), timer: $("timer"), score: $("score"),
  teamName: $("team-name"), title: $("round-title"), notice: $("notice"),
  hintCard: $("hint-card"), hintToggle: $("hint-toggle"), notesBody: $("notes-body"),
  hintList: $("hint-list"),
  overlayCodesTitle: $("overlay-codes-title"), overlayCodes: $("overlay-codes"),
  transcript: $("transcript"), chat: $("chat"), chatEmpty: $("chat-empty"),
  sendForm: $("send-form"), message: $("message"), sendBtn: $("send-btn"), sendNote: $("send-note"),
  micBtn: $("mic-btn"),
  guessForm: $("guess-form"), code: $("code"), guessBtn: $("guess-btn"), guessNote: $("guess-note"),
  stamp: $("stamp"), overlay: $("overlay"), overlayStamp: $("overlay-stamp"), overlayText: $("overlay-text"),
  hostBtn: $("host-btn"), hostDialog: $("host-dialog"), hostBody: $("host-body"),
  hostNote: $("host-note"), hostClose: $("host-close"),
};

const HOW_ENDED = {
  more_vaults: () => "Cracked more vaults.",
  faster_total: () => "Same number of vaults, but cracked them faster in total.",
  tiebreaker: () => "Won the tiebreaker.",
  host_award: () => "Awarded by the host.",
};

const REVEAL_HOW = { cracked: "cracked", skipped: "skipped by the host", unsolved: "not cracked" };

function revealText(r, names) {
  const vault = r.vault === null ? "Tiebreaker" : `Vault ${r.vault}`;
  return `${names[r.team]} · ${vault} · ${r.code} (${REVEAL_HOW[r.how] || r.how})`;
}

let state = null;
let chatKey = "";
let hostKey = "";
let pending = null;
let sending = false;
let guessing = false;
let hintsOpen = true;
let confirmNew = false;
let confirmEnd = false;
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

const isPlaying = (s) => s.phase === "round" || s.phase === "tiebreaker";
const canPlay = (s) => isPlaying(s) && !s.paused && !s.cracked_this_round[team];

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
    case "round": return s.round_name;
    case "intermission": return `Round ${s.round_number} is over`;
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
  const where = s.phase === "lobby" ? "" : s.round_number ? ` · Round ${s.round_number} of ${s.rounds_total}` : " · Tiebreaker";
  els.session.textContent = `Session ${s.session}${where}${s.paused ? " · Paused" : ""}`;
  els.teamName.textContent = isPlaying(s) ? `${names[team]} · ${s.difficulty}` : names[team];
  document.title = `${names[team]} · VaultBot`;
  els.title.textContent = titleFor(s);
  els.timer.textContent = s.seconds_left == null ? "--:--" : fmt(s.seconds_left);
  els.timer.classList.toggle("low", s.seconds_left != null && s.seconds_left <= 30 && !s.paused);
  els.score.textContent = `${names.a} ${s.rounds_cleared.a}/${s.rounds_total} · ${names.b} ${s.rounds_cleared.b}/${s.rounds_total}`;
  renderNotes(s, prev);
  renderNotice(s);
  renderChat(s);
  renderControls(s);
  renderOverlay(s);
  if (els.hostDialog.open) renderHost(s);
}

function renderNotes(s, prev) {
  const count = s.hints.length;
  els.hintCard.hidden = count === 0;
  if (count === 0) return;
  const before = prev && prev.session === s.session ? prev.hints.length : count;
  if (els.hintList.children.length !== s.hints.length) {
    els.hintList.replaceChildren(...s.hints.map((h) => el("li", {}, h)));
  }
  if (count > before) {
    hintsOpen = true;
    els.hintCard.classList.remove("arrive");
    void els.hintCard.offsetWidth;
    els.hintCard.classList.add("arrive");
  }
  els.notesBody.hidden = !hintsOpen;
  els.hintToggle.setAttribute("aria-expanded", String(hintsOpen));
  els.hintToggle.textContent = `${count} ${count === 1 ? "hint" : "hints"} (${hintsOpen ? "hide" : "show"})`;
}

function noticeFor(s) {
  if (isPlaying(s) && s.paused) return "Paused by the host. The clock is stopped.";
  if (s.phase === "round" && s.cracked_this_round[team]) {
    return `Vault cracked. Wait for ${s.team_names[other]} or for the clock to run out.`;
  }
  if (s.phase === "intermission" && s.next_round) return `Waiting for the host to start Round ${s.next_round.number}.`;
  return "";
}

function renderNotice(s) {
  const text = noticeFor(s);
  els.notice.hidden = !text;
  els.notice.textContent = text;
}

function emptyText(s) {
  if (s.phase === "lobby") return "Waiting for the host to start the session.";
  if (isPlaying(s)) return "No messages yet. Say hello to VaultBot, then try to get the code out of it.";
  if (s.phase === "intermission") return "Round over.";
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
  const active = canPlay(s);
  els.message.disabled = !active;
  els.sendBtn.disabled = !active || sending || s.busy;
  els.code.disabled = !active;
  if (!active || sending) cancelSpeech();
  els.micBtn.disabled = !active || sending;
  const wait = s.cooldown_s || 0;
  els.guessBtn.disabled = !active || guessing || wait > 0;
  els.guessBtn.textContent = wait > 0 ? `Try again in ${wait}s` : "Try this code";
}

function renderOverlay(s) {
  let stamp = "";
  let text = "";
  if (s.phase === "finished" && s.winner) {
    stamp = s.winner === team ? "YOU WIN" : "SESSION OVER";
    const how = HOW_ENDED[s.how_ended] ? HOW_ENDED[s.how_ended](s) : "";
    text = `${s.team_names[s.winner]} wins session ${s.session}. ${how}`;
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
  const unsolved = stamp ? s.reveals.filter((r) => r.how === "unsolved") : [];
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
  if (state) renderNotes(state, state);
});

els.message.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    els.sendForm.requestSubmit();
  }
});

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognizer = null;
let speechBase = "";
let speechFailed = false;

const SPEECH_ERRORS = {
  "no-speech": "No speech heard. Press Speak and try again.",
  "audio-capture": "No microphone found on this laptop.",
  "network": "Speech needs an internet connection. Type the message instead.",
  "language-not-supported": "This browser cannot recognise the language set in config.json.",
};

function speechErrorText(code) {
  if (code === "not-allowed" || code === "service-not-allowed") {
    return window.isSecureContext
      ? "The microphone is blocked. Allow it from the icon in the address bar, then press Speak."
      : "The browser blocks the microphone on this address. The README explains the Chrome setting that fixes it.";
  }
  return SPEECH_ERRORS[code] || "Speech stopped working. Type the message instead.";
}

function renderMic() {
  const on = recognizer !== null;
  els.micBtn.textContent = on ? "Stop" : "Speak";
  els.micBtn.setAttribute("aria-pressed", String(on));
  els.micBtn.classList.toggle("listening", on);
}

function startSpeech() {
  speechBase = els.message.value.trim();
  speechFailed = false;
  const rec = new Recognition();
  rec.lang = (state && state.speech_lang) || "en-US";
  rec.continuous = true;
  rec.interimResults = true;
  rec.onresult = (e) => {
    let said = "";
    for (const result of e.results) said += result[0].transcript;
    els.message.value = [speechBase, said.trim()].filter(Boolean).join(" ").slice(0, 500);
  };
  rec.onerror = (e) => {
    if (e.error === "aborted") return;
    speechFailed = true;
    note(els.sendNote, speechErrorText(e.error), true);
  };
  rec.onend = () => {
    if (recognizer !== rec) return;
    recognizer = null;
    renderMic();
    if (!speechFailed && els.message.value.trim()) note(els.sendNote, "Check the text, then press Send.");
  };
  recognizer = rec;
  try {
    rec.start();
  } catch {
    recognizer = null;
    note(els.sendNote, "Speech could not start. Type the message instead.", true);
  }
  renderMic();
  if (recognizer) note(els.sendNote, "Listening. Speak, then press Stop.");
}

// Drop anything still being recognised; the text box is the source of truth from here on.
function cancelSpeech() {
  if (!recognizer) return;
  const rec = recognizer;
  recognizer = null;
  rec.onresult = null;
  rec.abort();
  renderMic();
  note(els.sendNote, "");
}

if (Recognition) {
  els.micBtn.hidden = false;
  els.message.placeholder = "Write or speak to VaultBot. Enter sends, Shift+Enter adds a line.";
  els.micBtn.addEventListener("click", () => {
    if (recognizer) recognizer.stop();
    else startSpeech();
  });
  els.message.addEventListener("input", cancelSpeech);
}

els.sendForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  cancelSpeech();
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
  "start-round": () => `Round ${state.round_number} started.`,
  "end-round": () => "Round ended.",
  pause: () => "Paused. Both clocks and chats are frozen.",
  resume: () => "Resumed.",
  "add-time": (b) => `Added ${b.seconds / 60} min.`,
  "set-time": () => `Time left is now ${fmt(state.seconds_left)}.`,
  "show-hint": () => "Hint shown on both screens.",
  "round-minutes": () => "Round times saved.",
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
    confirmEnd = false;
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

function minutesField(id, label, value) {
  const input = el("input", { id, type: "number", min: "0.5", max: "60", step: "0.5", inputmode: "decimal" });
  input.value = String(value);
  return [el("label", { for: id }, label), input];
}

function readMinutes(id) {
  const value = parseFloat($(id).value);
  if (!(value > 0 && value <= 60)) {
    note(els.hostNote, "Use a number of minutes between 0.5 and 60.", true);
    return null;
  }
  return value;
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

function row(...children) {
  return el("div", { class: "host-row" }, ...children);
}

function clockSection(s) {
  const parts = [
    el("p", { id: "host-clock", class: "host-clock" }, clockText(s)),
    row(
      hostButton("+1 min", "add-time", { seconds: 60 }, "quiet"),
      hostButton("+3 min", "add-time", { seconds: 180 }, "quiet"),
      s.paused ? hostButton("Resume", "resume") : hostButton("Pause", "pause", {}, "quiet"),
    ),
  ];
  const setForm = el("form", { class: "host-form" },
    ...minutesField("set-minutes", "Set time left to (minutes)", Math.max(0.5, Math.round((s.seconds_left || 60) / 30) / 2)),
    el("button", { type: "submit", class: "quiet" }, "Set time left"));
  setForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const minutes = readMinutes("set-minutes");
    if (minutes) runHost("set-time", { seconds: Math.round(minutes * 60) });
  });
  parts.push(setForm);
  if (s.phase === "round") {
    if (!s.hint_given) parts.push(hostButton("Show this round's hint now", "show-hint", {}, "quiet"));
    if (confirmEnd) {
      parts.push(el("p", { class: "note alert" }, "Both teams stop now."));
      parts.push(hostButton(`Yes, end round ${s.round_number} now`, "end-round", {}, "danger"));
    } else {
      parts.push(el("button", { type: "button", class: "quiet", onclick: () => { confirmEnd = true; renderHost(state, true); } },
        "End this round now"));
    }
  }
  return section(s.phase === "tiebreaker" ? "Tiebreaker clock" : `Round ${s.round_number} clock`, ...parts);
}

function clockText(s) {
  if (s.seconds_left == null) return "";
  return `${fmt(s.seconds_left)} left${s.paused ? " (paused)" : ""}`;
}

function startSection(s) {
  const nxt = s.next_round;
  const parts = [...minutesField("start-minutes", `Round ${nxt.number} time (minutes)`, nxt.minutes)];
  for (const opt of nxt.options) {
    const label = nxt.options.length > 1
      ? `Start round ${nxt.number}: ${opt.difficulty} (${opt.title})`
      : `Start round ${nxt.number}`;
    parts.push(el("button", {
      type: "button",
      class: opt === nxt.options[0] ? "" : "quiet",
      onclick: () => {
        const minutes = readMinutes("start-minutes");
        if (minutes) runHost("start-round", { minutes, variant: opt.variant });
      },
    }, label));
  }
  const repeat = nxt.options.find((o) => o.variant !== nxt.number);
  if (repeat) {
    parts.push(el("p", { class: "note" }, `${repeat.difficulty} uses the Round ${repeat.variant} guard again with a new code, for teams that need an easier finish.`));
  }
  return section(`Next: Round ${nxt.number} of ${s.rounds_total}`, el("div", { class: "host-form" }, ...parts));
}

function lobbySection(s) {
  const n = s.team_names;
  const names = { a: n.a, b: n.b };
  const nameForm = el("form", { class: "host-form" },
    ...nameField("rename-a", "Name on screen A", n.a, (v) => { names.a = v; }),
    ...nameField("rename-b", "Name on screen B", n.b, (v) => { names.b = v; }),
    el("button", { type: "submit", class: "quiet" }, "Save names"));
  nameForm.addEventListener("submit", (e) => { e.preventDefault(); runHost("rename", names); });

  const timeFields = s.base_minutes.flatMap((m, i) => minutesField(`base-${i}`, `Round ${i + 1} base time (minutes)`, m));
  const timeForm = el("form", { class: "host-form" }, ...timeFields,
    el("button", { type: "submit", class: "quiet" }, "Save round times"));
  timeForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const values = s.base_minutes.map((_, i) => readMinutes(`base-${i}`));
    if (values.every((v) => v)) runHost("round-minutes", { round_minutes: values });
  });
  return [section("Team names", nameForm), section("Round times", timeForm)];
}

function resultSection(s) {
  const n = s.team_names;
  const parts = [];
  if (s.phase === "tie") {
    parts.push(el("p", {}, `Vaults: ${n.a} ${s.rounds_cleared.a}, ${n.b} ${s.rounds_cleared.b}. Total crack time: ${n.a} ${fmt(Math.round(s.total_time.a))}, ${n.b} ${fmt(Math.round(s.total_time.b))}.`));
    const form = el("form", { class: "host-form" }, ...minutesField("tb-minutes", "Tiebreaker time (minutes)", s.tiebreaker_minutes),
      el("button", { type: "submit" }, "Start the tiebreaker"));
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const minutes = readMinutes("tb-minutes");
      if (minutes) runHost("tiebreaker", { minutes });
    });
    parts.push(form,
      hostButton(`Award the win to ${n.a}`, "award", { team: "a" }, "quiet"),
      hostButton(`Award the win to ${n.b}`, "award", { team: "b" }, "quiet"));
  } else if (s.phase === "tiebreak_over") {
    parts.push(
      el("p", {}, `Wrong guesses in the tiebreaker: ${n.a} ${s.tiebreak_wrong.a}, ${n.b} ${s.tiebreak_wrong.b}. Fewer wrong guesses wins.`),
      hostButton(`Award the win to ${n.a}`, "award", { team: "a" }),
      hostButton(`Award the win to ${n.b}`, "award", { team: "b" }));
  } else if (s.phase === "finished") {
    parts.push(el("p", {}, s.winner ? `${n[s.winner]} won session ${s.session}. It is saved on the results page.` : `Session ${s.session} ended.`));
  }
  return parts.length ? [section(`Session ${s.session} result`, ...parts)] : [];
}

function nextSessionSection(s) {
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
  form.append(el("button", { type: "submit", class: stillPlaying && confirmNew ? "danger" : "quiet" }, label));
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
  const key = [s.session, s.phase, s.paused, s.round_number, s.hint_given, hostPin ? 1 : 0, confirmNew, confirmEnd].join("|");
  if (!force && key === hostKey) {
    const clock = $("host-clock");
    if (clock) clock.textContent = clockText(s);
    return;
  }
  if (!force && hostKey) note(els.hostNote, "");
  hostKey = key;
  if (!hostPin) { els.hostBody.replaceChildren(pinForm()); return; }
  const parts = [];
  if (isPlaying(s)) parts.push(clockSection(s));
  if (s.next_round) parts.push(startSection(s));
  if (s.phase === "lobby") parts.push(...lobbySection(s));
  parts.push(...resultSection(s));
  if (s.phase !== "lobby") parts.push(nextSessionSection(s));
  els.hostBody.replaceChildren(...parts);
}

els.hostBtn.addEventListener("click", () => {
  confirmNew = false;
  confirmEnd = false;
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
