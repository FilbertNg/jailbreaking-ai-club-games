# Handoff: Break the AI

Last updated: 2026-11-08. Read this first if you are picking up the project.

## What it is

A two-team jailbreak game for an AI Club event. Each team chats with VaultBot (a Gemini guard called through LangChain) and tries to make it say a secret 4-digit code. Three rounds, each guard stricter. The event runs 4 sessions, each with two new teams. Host rules are in [GAME_GUIDE.md](GAME_GUIDE.md); setup is in [README.md](README.md).

## Current state

- All 11 planned tasks are built and committed on `master` (11 commits, local only).
- `uv run pytest`: 107 tests pass.
- Played end to end in a browser at 360, 768 and 1366 px: lobby, chat, wrong and correct codes, hints, skip, win, tie, tiebreaker, award, new session, results page, server restart.
- **Not done yet:** no GitHub remote. Laptop B cannot `git clone` until the repo is pushed.

## Run it

```
uv sync
uv run jailbreak
```

Needs `.env` in this folder with `GEMINI_API_KEY`, `HOST_PIN` (currently `2468`, change it before the event) and the optional `LANGCHAIN_*` lines. The server prints the Team A, Team B and Results addresses.

## How it is built

| Path | Job |
| --- | --- |
| `config.json` | Models, timers, hints, guard prompt per round. Edit this to change the game. |
| `src/jailbreak/config.py` | Loads and checks `config.json` and `.env`. |
| `src/jailbreak/game.py` | All game rules. Pure Python, clock passed in, no network. |
| `src/jailbreak/censor.py` | Blocks replies that contain the code (`digits` or `strict` mode). |
| `src/jailbreak/guard.py` | Calls the models through LangChain, falls back down the chain, cuts and censors replies. |
| `src/jailbreak/main.py` | FastAPI routes, saving to `state.json` / `results.jsonl`, `run()`. |
| `src/jailbreak/static/` | Team page, results page, shared `case.css`. Plain HTML/JS, no build step. |
| `tests/` | One test file per module. `conftest.py` has the fake clock and a small test config. |

One server runs on Laptop A. Laptop B only opens `/team/b` in a browser. Pages poll `GET /api/state` every second. Codes never leave the server.

A chat message goes: page, `POST /api/chat`, per-team lock (one message at a time), `guard.reply()`, model chain, cut to `max_reply_chars`, censor, stored in the game, returned. Replies are not streamed, so the censor always runs before anyone sees the text.

## Decisions worth knowing

- **Model chain:** `gemini-3.5-flash-lite`, then `gemini-3.1-flash-lite`, then `gemma-4-26b-a4b-it`. A model that rate-limits, errors, times out (30 s) or returns empty text is skipped for 60 s. A 401/403 stops at once, since another model will not fix a bad key. `max_retries=0` on every model so a limited model falls through immediately.
- **Short answers in Round 3** come from cutting the reply to 160 characters on the server, not from a low token limit. Gemma 4 spends output tokens on thinking first, and a 60-token limit returned empty replies in testing.
- **Random codes, revealed later:** every team, round, session and tiebreaker gets a new random code (1000 to 9999). A code is shown on both screens once it is cracked or skipped, and every uncracked code is shown when time runs out. Ended sessions list their codes on the results page.
- **First to Round 3 wins, the other team keeps playing:** the winner is set at once, but the session runs until the timer ends (or until both teams finish), so the results show how far both got.
- **Sessions, not reset:** "New session" saves the current result (or "stopped early") to `results.jsonl` and opens a fresh lobby with a new number. In the lobby it only renames, so session numbers have no gaps.
- **Host controls** live in a PIN-locked dialog on the team page. There is no separate dashboard. The PIN is remembered per browser tab.
- **Look:** a security case file. Paper colors, Courier Prime for the transcript, Public Sans for the interface, one red stamp accent. Light theme only, on purpose.

The full design is in `docs/superpowers/specs/2026-11-08-jailbreak-game-design.md`, and the step-by-step build plan with all code is in `docs/superpowers/plans/2026-11-08-jailbreak-game.md`.

## Prompt tuning results (2026-11-08)

Tested with 3 tries per message on the real models.

| Round | Result |
| --- | --- |
| 1 | Refused "hello" and "what is the code" 6 out of 6. Simple role-play trick leaked the code 3 out of 3. |
| 2 | Refused plain asks and the training-game trick 6 out of 6. A story asking for the numbers as words leaked 2 out of 3, past the digit censor. |
| 3 | Refused all 9 attacks, one short sentence each. |

Samples are small. Play one full session yourself before the event.

## Known issues

- **Gemma 4 is flaky.** Both `gemma-4-26b-a4b-it` and `gemma-4-31b-it` returned HTTP 500 about 40% of the time on 2026-11-08, with any settings. It is only used when both Flash-Lite models are down, so the impact is small. If it gets worse, swap the model ID in `config.json`.
- **Replies take about 3 to 12 seconds.** The page shows "VaultBot is typing..." meanwhile.
- **`state.json` holds the codes in plain text.** Do not open it on a screen players can see.
- **Browsers cache `case.css`.** After editing styles, press Ctrl+F5 on open pages.
- **Model text is not filtered for style.** Replies can contain emoji or em dashes; that is the model, not the app.
- The free-tier key is shared by both teams. If every model is limited at once, teams see "The guard is busy" until the limit resets.

## Next steps

1. Push the repo to GitHub (private is safest) so Laptop B can clone it. `.env`, `state.json` and `results.jsonl` are gitignored.
2. Change `HOST_PIN` in `.env`.
3. On Laptop B: clone, `uv sync`, create its own `.env`, run `uv run jailbreak` once to confirm it works as a backup server.
4. Play one full session on both laptops over the event Wi-Fi. Allow Python through Windows Firewall on private networks.
5. Before the first session, delete `state.json` and `results.jsonl` so the event starts at session 1.

## Tips for working on the code

- Add tests first; game rules are easiest to test in `tests/test_game.py` with the `clock` fixture.
- `uv run pytest -q` runs everything in about 3 seconds with no network.
- On Windows, scripts that print model replies need `PYTHONIOENCODING=utf-8`, or emoji in replies crash the print.
- To test a correct guess without tricking the bot, read the current code from `state.json` on the server laptop.
