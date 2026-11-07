const archive = document.getElementById("archive");
const status = document.getElementById("status");
const conn = document.getElementById("conn-bar");
let loadedOnce = false;

const PHASE_WORDS = {
  lobby: "Waiting to start",
  running: "Playing now",
  tie: "Tie, waiting for the tiebreaker",
  tiebreaker: "Tiebreaker running",
  tiebreak_over: "The host is choosing the winner",
};

function fmt(seconds) {
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function el(tag, cls, ...children) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  node.append(...children);
  return node;
}

function howText(r) {
  const w = r.winner ? r.teams[r.winner] : null;
  const other = r.winner ? r.teams[r.winner === "a" ? "b" : "a"] : null;
  switch (r.how_ended) {
    case "cracked_all": return `Cracked all ${r.rounds_total} vaults at ${fmt(w.clear_times.at(-1))}.`;
    case "more_rounds": return "More vaults cracked when time ran out.";
    case "faster_clear": return `Same number of vaults. Last one cracked at ${fmt(w.clear_times.at(-1))} against ${fmt(other.clear_times.at(-1))}.`;
    case "tiebreaker": return "Won the tiebreaker.";
    case "host_award": return "Awarded by the host after a tie.";
    default: return "Stopped early. No winner.";
  }
}

function sides(teams, total, winner) {
  return el("div", "sides", ...["a", "b"].map((t) => el("p", `side${winner === t ? " won" : ""}`,
    el("span", "", teams[t].name),
    el("span", "vaults", `${teams[t].rounds_cleared}/${total} vaults`))));
}

function recordEntry(r) {
  const ended = new Date(r.ended_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const verdict = r.winner
    ? el("p", "verdict", `${r.teams[r.winner].name} won`)
    : el("p", "verdict none", "No winner");
  return el("li", "entry",
    el("div", "", el("p", "entry-num", `Session ${r.session}`), el("p", "entry-when", `Ended ${ended}`)),
    sides(r.teams, r.rounds_total, r.winner),
    verdict,
    el("p", "how", howText(r)));
}

function liveEntry(c) {
  const clock = c.seconds_left == null ? "" : `, ${fmt(c.seconds_left)} left`;
  return el("li", "entry live",
    el("div", "", el("p", "entry-num", `Session ${c.session}`), el("p", "entry-when", "In progress")),
    sides(c.teams, c.rounds_total, null),
    el("p", "verdict none", PHASE_WORDS[c.phase] + clock));
}

function render(data) {
  const items = [];
  if (data.current && data.current.phase !== "finished") items.push(liveEntry(data.current));
  items.push(...data.sessions.map(recordEntry));
  archive.replaceChildren(...items);
  status.hidden = data.sessions.length > 0;
  status.textContent = "No sessions played yet. Results appear here when a session ends.";
}

async function load() {
  try {
    const res = await fetch("/api/results");
    if (!res.ok) throw new Error(String(res.status));
    render(await res.json());
    loadedOnce = true;
    conn.hidden = true;
  } catch {
    if (loadedOnce) conn.hidden = false;
    else status.textContent = "Could not reach the game server. Retrying.";
  }
}

load();
setInterval(load, 5000);
