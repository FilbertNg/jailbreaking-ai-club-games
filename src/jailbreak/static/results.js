const archive = document.getElementById("archive");
const status = document.getElementById("status");
const conn = document.getElementById("conn-bar");
let loadedOnce = false;

const PHASE_WORDS = {
  lobby: () => "Waiting to start",
  round: (c) => `Round ${c.round_number} of ${c.rounds_total}`,
  intermission: (c) => `Between rounds (${c.round_number} of ${c.rounds_total} done)`,
  tie: () => "Tie, waiting for the tiebreaker",
  tiebreaker: () => "Tiebreaker running",
  tiebreak_over: () => "The host is choosing the winner",
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
  let text;
  switch (r.how_ended) {
    case "more_points": text = "Scored more points."; break;
    case "more_vaults": text = "Cracked more vaults."; break;
    case "faster_total": text = `Same number of vaults, cracked in ${fmt(w.total_time)} total against ${fmt(other.total_time)}.`; break;
    case "tiebreaker": text = "Won the tiebreaker."; break;
    case "host_award": text = "Awarded by the host after a tie."; break;
    case "stopped_early": text = "Stopped early. No winner."; break;
    default: text = r.winner ? "Won." : "No winner.";
  }
  if (r.plan && r.plan.length) text += ` Difficulty: ${r.plan.join(", ")}.`;
  return text;
}

function sideScore(team, total) {
  const vaults = `${team.rounds_cleared}/${total} vaults`;
  const points = team.total_points ?? team.points;
  return points === undefined ? vaults : `${points} pts, ${vaults}`;
}

function sides(teams, total, winner) {
  return el("div", "sides", ...["a", "b"].map((t) => el("p", `side${winner === t ? " won" : ""}`,
    el("span", "", teams[t].name),
    el("span", "vaults", sideScore(teams[t], total)))));
}

function codeLines(r) {
  const reveals = r.reveals || [];
  const order = (v) => (v === null ? 99 : v);
  return ["a", "b"].flatMap((t) => {
    const mine = reveals.filter((x) => x.team === t).sort((x, y) => order(x.vault) - order(y.vault));
    if (!mine.length) return [];
    const items = mine.map((x) => {
      const label = x.vault === null ? `tiebreaker ${x.code}` : x.code;
      const how = x.how === "skipped" ? " (skipped)" : x.how === "unsolved" ? " (not cracked)" : x.how === "rule_broken" ? " (rule broken)" : "";
      return label + how;
    });
    return [el("p", "codes", `${r.teams[t].name} codes: ${items.join(", ")}`)];
  });
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
    el("p", "how", howText(r)),
    ...codeLines(r));
}

function liveEntry(c) {
  const clock = c.seconds_left == null ? "" : `, ${fmt(c.seconds_left)} left`;
  const words = PHASE_WORDS[c.phase] ? PHASE_WORDS[c.phase](c) : "In progress";
  return el("li", "entry live",
    el("div", "", el("p", "entry-num", `Session ${c.session}`), el("p", "entry-when", "In progress")),
    sides(c.teams, c.rounds_total, null),
    el("p", "verdict none", words + clock + (c.paused ? ", paused" : "")));
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
