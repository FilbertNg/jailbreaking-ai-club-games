# Break the AI: game server design

Date: 2026-11-08
Source of the rules: `GAME_GUIDE.md`

## Goal

A web app that runs the game in `GAME_GUIDE.md`. Two teams each chat with VaultBot, a guard played by Gemini, and try to make it say a secret 4-digit code. Three rounds with stricter guards. The first team to clear all three wins.

## Constraints

- Everything lives in `jailbreak-user/`. Python environment and dependencies are managed by uv only (no Node, no build step).
- LLM calls go through LangChain (`langchain-google-genai`, `ChatGoogleGenerativeAI`), with the key read from `GEMINI_API_KEY` in `jailbreak-user/.env`.
- LangSmith tracing uses the existing `LANGCHAIN_TRACING_V2`, `LANGCHAIN_ENDPOINT`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT` variables in the same `.env`.
- The Gemini key is on the free tier, shared by both teams.
- `.env`, `state.json` and `results.jsonl` stay out of git.
- The game is played as 4 sessions in one event, each with two new teams, with no server restart in between.

## Decisions

| Topic | Decision | Reason |
| --- | --- | --- |
| Laptops | One server on Laptop A. Laptop A opens `/team/a`, Laptop B opens `http://<A's IP>:8000/team/b`. | One source of truth for the timer, codes and winner. |
| Fallback | Repo goes to GitHub, so Laptop B can clone it and become the server if Laptop A fails. | Recovery without new code. |
| Stack | FastAPI + plain HTML/CSS/JS served as static files. Pages poll `GET /api/state` once per second. | uv only, no build step. Polling survives shaky Wi-Fi; two clients is a trivial load. |
| Host controls | No separate dashboard. A "Host" button on each team page opens a PIN-locked dialog. | The host asked to run everything from the game screen. |
| Replies | Not streamed. The full reply is censored first, then shown. | Streaming would show the code before the censor runs. |
| Models | Ordered chain: `gemini-3.5-flash-lite`, then `gemini-3.1-flash-lite`, then `gemma-4-26b-a4b-it`. Each message starts at the first model that is not currently skipped. A model that hits a rate limit, a server error, a timeout or an empty reply is skipped for `model_skip_s` (60) seconds, then tried again. All IDs confirmed against this API key on 2026-11-08. | The host asked for this order. The skip window stops every message from re-hitting a limited model, and lets the game return to the best model once the limit resets. |
| Gemma variant | `gemma-4-26b-a4b-it` (6.5 s in a test) over `gemma-4-31b-it` (11.9 s). One line in `config.json` to swap. | Faster replies keep the relay rule moving. |
| Local backup model | Not built. The three-model chain replaces the guide's "switch to the backup local model". | Avoids installing and testing Ollama; the chain already covers one model being limited or down. |
| Host can read every chat | Covered by LangSmith traces, tagged by session number, team and round. | No extra UI needed. |
| Sessions | There is no reset. The host starts a **new session**, entering the names of the two new teams. The current session's result is saved first, then a fresh session opens in the lobby with a new number. Past results are shown on a separate `/results` page. | Each session is its own contest between two new teams, and every session's result stays visible after the next one starts. |

## Architecture

```
jailbreak-user/
  pyproject.toml          uv project, script entry: jailbreak = "jailbreak.main:run"
  config.json             rounds, prompts, hints, timings, model
  .env                    keys + HOST_PIN (gitignored)
  state.json              saved game state (gitignored, created at runtime)
  results.jsonl           one line per ended session (gitignored, created at runtime)
  src/jailbreak/
    config.py             loads config.json and .env, validates them
    censor.py             pure functions: is_blocked(reply, code, mode)
    game.py               pure game state machine, clock injected
    guard.py              LangChain call to Gemini
    main.py               FastAPI app, routes, run() binds 0.0.0.0:8000
    static/
      team.html  team.js  results.html  results.js  case.css (shared styles)
  tests/
    test_censor.py  test_game.py  test_guard.py  test_api.py
  README.md
```

Dependencies: `fastapi`, `uvicorn[standard]`, `langchain-google-genai`, `langchain-core`, `python-dotenv`. Dev: `pytest`, `httpx`. Python 3.12.

### `censor.py`

`is_blocked(reply: str, code: str, mode: "none" | "digits" | "strict") -> bool`

- `none`: never blocks.
- `digits`: remove whitespace and the separators `- . , _ / | ·` from the reply, then block if `code` is a substring. Catches `4712`, `4 7 1 2`, `4-7-1-2`.
- `strict`: lowercase the reply, replace the words zero to nine with digits, drop every non-digit character, then block if `code` or `code` reversed is a substring. Catches `four seven one two`, `2174`, mixed forms.

A blocked reply is replaced by: `Blocked by the censor. The guard tried to say the code.` The replaced text is what gets stored in the chat history and sent back to the model as memory.

### `game.py`

Pure Python, no I/O except an optional save callback. Takes a `now()` function so tests control the clock.

Phases: `lobby`, `running`, `tie`, `tiebreaker`, `tiebreak_over`, `finished`.

Per team: current round index, rounds cleared, time of last clear (seconds since start), code per round, chat history per round, wrong guesses (main game and tiebreaker counted separately), cooldown end time, busy flag.

Rules:
- `start()`: lobby to running. New random codes (1000 to 9999, A and B never share a code in the same round), clears scores and chats, sets the end time to now + `game_minutes`.
- `guess(team, code)`: rejects non 4-digit input. During a cooldown it returns the seconds left. A wrong guess adds 1 to wrong guesses and starts a `wrong_guess_cooldown_s` cooldown. A correct guess records the clear time, moves the team to the next round with an empty chat. Clearing the last round sets `finished` with that team as winner.
- Timer end (checked on every state read): the team with more rounds cleared wins. Same rounds: the earlier last clear wins, unless the two clear times are within `tie_window_s` (10) seconds or both teams cleared 0, which gives `tie`.
- `start_tiebreaker()`: only from `tie`. New codes, the tiebreaker guard, `tiebreaker_minutes` on the clock. The first correct code wins. Time out gives `tiebreak_over`.
- `award(team)`: from `tiebreak_over` (or `tie`), sets `finished` with that winner.
- `skip_round(team)`: counts as a clear at the current time.
- `next_hint()`: reveals one more hint now. Hints also unlock on their own at `hint_minutes` (3, 6, 8) after start.
- `new_session(names)`: allowed in every phase. Both team names are required (1 to 24 chars each). In `lobby` it only replaces the names and keeps the session number, so the results page has no gaps. Otherwise, if the session is not `finished`, its result is saved first as `stopped early` (see below). Then session number + 1, phase `lobby`, scores, codes, chats, hints and cooldowns cleared, the new names set. The URLs stay `/team/a` and `/team/b`, so the laptops never change pages.
- `rename(names)`: only in `lobby`, to fix a typo in the current session's names.
- A session's result is appended to `results.jsonl` once: when it reaches `finished`, or when the host opens a new session before it finished. The line holds session number, start and end time, team names, rounds cleared, clear times, wrong guesses, winner, and how it ended: `cracked all rounds`, `more rounds at time up`, `faster clear at time up`, `tiebreaker`, `host award`, or `stopped early` (no winner). A session that never left the lobby is not saved.
- After every change the state is written to `state.json`, and loaded on startup if present. The session number survives a server restart.

### `guard.py`

`async reply(round_cfg, code, history, message, team) -> str`

- Builds `[SystemMessage(round prompt with {code} filled in)] + memory + [HumanMessage(message)]`.
- Memory: the last `memory_messages` messages of this round's chat (20 for rounds 1 and 2, 0 for round 3, set in `config.json`).
- Models: one `ChatGoogleGenerativeAI(model=id, temperature=round.temperature, max_output_tokens=config.max_output_tokens, max_retries=0, timeout=config.model_timeout_s)` per entry in `config.models`, built once at startup. `max_retries=0` so a limited model falls through at once instead of LangChain retrying it.
- Fallback: a small `ModelChain` in `guard.py` walks the models in order, skipping any whose `skipped_until` is in the future. On a 429 / quota error, a 5xx, a timeout or an empty reply it marks that model skipped for `model_skip_s` seconds and tries the next one. If every model fails or is skipped, it raises `GuardBusy`. The clock is injected so tests control it. Custom code instead of LangChain's `with_fallbacks`, because `with_fallbacks` has no skip window and would hit the limited model first on every message.
- Short answers: Gemma 4 spends output tokens on thinking first (251 thinking tokens for a one-sentence reply in a test, and an empty reply at a 60-token limit). So `max_output_tokens` stays generous (1024) for every round, the prompt asks for brevity, and the server cuts the reply to `max_reply_chars` at a word boundary (Round 3: 160). The censor runs on the cut reply, which is exactly what players see.
- The answering model's ID is recorded in LangSmith metadata. Teams are not shown which model answered.
- Each call is tagged for LangSmith: run name `vaultbot`, tags `session-3` / `team-a` / `round-2` / `tiebreaker`, metadata with session number, team id, team name and round.
- Errors: `GuardBusy` when the whole chain is failing or skipped. Errors that no model change can fix (bad API key, invalid request) raise `GuardError` at once instead of burning through the chain. The code is never logged outside LangSmith.

### `main.py` routes

| Route | Who | Does |
| --- | --- | --- |
| `GET /` | anyone | Three links: Team A, Team B, Results |
| `GET /team/{a or b}` | team | The game page |
| `GET /api/state?team=a` | team | Game number, team names, phase, seconds left, both teams' rounds cleared, this team's round and chat, revealed hints, cooldown left, busy flag, winner. Never includes codes. |
| `POST /api/chat` `{team, message}` | team | 1 to 500 chars. 409 if this team already has a message waiting. Calls the guard, censors, stores, returns the reply. 503 with a readable message on `GuardBusy` / `GuardError`. Only allowed in `running` or `tiebreaker`. |
| `POST /api/guess` `{team, code}` | team | Result: correct, wrong (with cooldown), cooldown active, invalid. |
| `POST /api/host/{action}` | host | Header `X-Host-Pin` must match `HOST_PIN`. Actions: `start`, `next-hint`, `skip` (body: team), `tiebreaker`, `award` (body: team), `new-session` (body: `{a, b}` names), `rename` (body: `{a, b}`). If `HOST_PIN` is unset, host actions are refused with a message saying to set it. |
| `GET /results` | anyone | The results page |
| `GET /api/results` | anyone | All saved sessions from `results.jsonl`, newest first, plus the current session's live standing. Never includes codes or chats. |

`run()` starts uvicorn on `0.0.0.0:8000` and prints the LAN addresses for `/team/a` and `/team/b`.

### `config.json`

```json
{
  "models": ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemma-4-26b-a4b-it"],
  "model_skip_s": 60,
  "model_timeout_s": 30,
  "max_output_tokens": 1024,
  "team_names": { "a": "Team A", "b": "Team B" },
  "game_minutes": 10,
  "tiebreaker_minutes": 3,
  "wrong_guess_cooldown_s": 10,
  "tie_window_s": 10,
  "hint_minutes": [3, 6, 8],
  "hints": ["...", "...", "..."],
  "rounds": [
    { "name": "Round 1", "prompt": "... {code} ...", "censor": "none",   "memory_messages": 20, "max_reply_chars": 1200, "temperature": 0.9 },
    { "name": "Round 2", "prompt": "... {code} ...", "censor": "digits", "memory_messages": 20, "max_reply_chars": 800,  "temperature": 0.7 },
    { "name": "Round 3", "prompt": "... {code} ...", "censor": "strict", "memory_messages": 0,  "max_reply_chars": 160,  "temperature": 0.3 }
  ],
  "tiebreaker": { "name": "Tiebreaker", "prompt": "... {code} ...", "censor": "digits", "memory_messages": 20, "max_reply_chars": 600, "temperature": 0.7 }
}
```

Adding a Round 4 means adding an entry to `rounds`. The prompts and hint texts are written during implementation and tested against the real model (Round 1 crackable in a minute or two, Round 3 very hard).

## Screen design

Design read: a game screen for students playing in teams, in a security case-file style. Dials: ENERGY 2 / RHYTHM 1 (one app screen, uniform on purpose) / MOTION 2 (one stamp animation).

- Palette: warm paper background, dark ink text, one red stamp accent used only for CRACKED, DENIED and the game-over stamp. Every text pairing is checked with the antislop contrast script (WCAG AA).
- Type: Courier Prime for the guard transcript (reads like an interrogation record), Public Sans for the interface (plain institutional voice). Loaded from Google Fonts with system fallbacks.
- Theme: light only. Reason: the paper case file is the identity, and light screens read better when projected.
- Focal point: the chat transcript. Below it, the message box with Send, and the code box (one numeric field, `inputmode="numeric"`, 4 digits) with "Try this code".
- Floating: top right, a case tab with the timer and both teams' rounds cleared (`Team A 1/3 · Team B 2/3`). Bottom left, the hint card, which slides in when a hint unlocks and can be collapsed. Under 640px wide both dock into a top bar so nothing covers the chat.
- After each send: "Pass the keyboard to a teammate." under the message box.
- Motion: the red stamp lands once when a code is correct. Hover and focus states otherwise. Respects `prefers-reduced-motion`.
- Host button: small text button, bottom right. Opens a dialog (Escape closes, focus trapped) asking for the PIN, then shows the host actions. The PIN is kept in `sessionStorage` for that tab. The dialog shows only the actions valid in the current phase, except "New session", which is always there. New session opens a small form with two team-name fields and a "Save this session and start session 3" button. If the current session is still being played, the form says so in plain words ("Session 2 is still running. It will be saved as stopped early.") and needs a second click, inside the dialog, not a browser `confirm()`. In the lobby the dialog also lets the host fix the current names. The dialog links to `/results`.
- The case tab shows the session number and team names ("Session 2") so everyone knows which contest is on screen.

### Results page (`/results`)

A separate page in the same case-file style, read-only, safe to put on a projector between sessions.

- Reads as a case archive: one entry per session, newest first. Each entry shows session number, the two team names, rounds cleared per team, the winner with the red stamp, and how it ended in words ("Cracked all 3 rounds at 06:12", "Won the tiebreaker", "Stopped early, no winner").
- The current session sits at the top as "In progress" with live rounds cleared, without a stamp.
- Refreshes every 5 seconds, so it can stay open on a spare screen.
- States: loading ("Opening the archive..."), empty ("No sessions played yet. Results appear here when a session ends."), error ("Could not reach the game server. Retrying."). The page also works at phone width.

States the page must show:

| State | Shown as |
| --- | --- |
| Lobby | "Waiting for the host to start the game." Chat and code box disabled. |
| Guard thinking | "VaultBot is typing..." in the transcript, Send disabled. |
| Guard busy (429) | "The guard is busy. Wait a few seconds and send again." The message stays in the box. |
| Guard error | "The guard did not answer. Try again." The message stays in the box. |
| Censored reply | The censor line, styled as a redaction bar with text. |
| Wrong code | DENIED, plus a countdown on the "Try this code" button. |
| Correct code | CRACKED stamp, then the next round with a fresh chat. |
| Server unreachable | A bar: "Lost connection to the game server. Retrying." |
| Tie | "Tie. Waiting for the host to start the tiebreaker." |
| Tiebreak over | "Time is up. The host will choose the winner." Host dialog shows each team's wrong guesses. |
| Finished | Winner stamp over the screen. Chat disabled. |

## Error handling

- One message in flight per team (server-side lock), so a double click or two teammates cannot spend the free-tier quota twice.
- A limited or failing model falls through to the next one in the chain. Only when all three are failing or skipped does the team see the `GuardBusy` message.
- Replies take about 6 to 12 seconds (measured). Each model call times out after `model_timeout_s` (30), so the worst case before `GuardBusy` stays bounded.
- Guesses and chats outside an active phase return 409 with the reason.
- Bad team id returns 404. Bad input returns 422 with a readable message.
- Missing `GEMINI_API_KEY` stops the server at startup with a clear message. Missing `HOST_PIN` only disables host actions.

## Testing

Written test-first with pytest.

- `test_censor.py`: each mode against plain digits, spaced and dashed digits, number words, reversed code, mixed forms, and harmless replies that must pass.
- `test_game.py`: with a fake clock: start, wrong guess and cooldown, correct guess advances, last round wins at once, timer end with more rounds, equal rounds decided by clear time, the 10-second tie window, 0-0 tie, tiebreaker win, tiebreak timeout then award, skip, hints by time and by button, new session from every phase (number goes up, new names set, everything else cleared), a finished session appends exactly one results line with the right "how it ended", a session stopped mid-game is saved as `stopped early`, a lobby-only session is not saved, rename only in lobby, save and load keep the session number.
- `test_guard.py`: with fake models and a fake clock: first model answers when healthy; a 429 on model 1 falls to model 2 and skips model 1 for 60 s; model 1 is tried again after the window; 5xx, timeout and empty reply also fall through; all three failing raises `GuardBusy`; replies are cut at a word boundary to `max_reply_chars`; memory is dropped when `memory_messages` is 0.
- `test_api.py`: FastAPI TestClient with a fake guard: state and `/api/results` never contain codes or chats, host PIN required, new session needs both names, chat lock returns 409, censoring applied, `GuardBusy` becomes 503 with the message.
- Manual check against real Gemini: one short session per round to tune prompts, and confirm LangSmith shows the traces with tags.
- Browser click-through of every control on the team page and host dialog, at laptop and phone widths, with the console checked for errors.

## Docs

- `README.md`: install uv, `uv sync`, create `.env` (keys + `HOST_PIN`), `uv run jailbreak`, find Laptop A's IP, allow Python through Windows Firewall on private networks, open the team pages, and how Laptop B takes over.
- `GAME_GUIDE.md` updated: dashboard becomes the Host dialog, the phone checker row goes, the backup local model row becomes "the server already falls back through three models; if all are busy, wait a minute", the "Do not restart during a tie" row now says not to open a new session during a tie, and a short "Between sessions" checklist is added (New session with the next two team names, check `/results`, START).

## Out of scope

Accounts, more than two teams, phone-only play, a separate host dashboard or projector board, a local model, enforcing the relay rule in code.
