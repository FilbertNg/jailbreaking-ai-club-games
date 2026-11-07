# Break the AI

A two-team game: each team chats with VaultBot, a guard played by Gemini, and tries to make it say a secret 4-digit code. Three rounds, each guard stricter than the last. Rules for the host are in [GAME_GUIDE.md](GAME_GUIDE.md).

## How it runs

Laptop A runs the server and shows Team A's screen. Laptop B opens Team B's screen from Laptop A over the same Wi-Fi. Both laptops have the code from GitHub, so Laptop B can take over as the server if Laptop A fails.

## Setup (each laptop, once)

1. Install uv: https://docs.astral.sh/uv/getting-started/installation/
2. Get the code: `git clone <repo URL>` and `cd jailbreak-user`
3. Install: `uv sync`
4. Create `.env` in this folder (it is never committed):

   ```
   GEMINI_API_KEY=your Gemini API key
   HOST_PIN=a PIN only the host knows

   LANGCHAIN_TRACING_V2=true
   LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
   LANGCHAIN_API_KEY=your LangSmith key
   LANGCHAIN_PROJECT=your LangSmith project name
   ```

   The LangSmith lines are optional. With them, every chat is saved in LangSmith, tagged by session, team and round.

## On the day

1. On Laptop A: `uv run jailbreak`. Keep the window open. It prints the addresses.
2. The first time, Windows asks whether Python may use the network. Allow it on **private networks**. If Laptop B cannot connect, check that the Wi-Fi is set to a private network on Laptop A.
3. Laptop A opens `http://localhost:8000/team/a`.
4. Laptop B opens the `Laptop B` address from the server window, for example `http://192.168.1.23:8000/team/b`.
5. Any spare screen can open the `Results page` address.

### Speaking to the guard

The **Speak** button turns speech into text in the message box; the team checks it and presses Send. It needs Chrome or Edge and an internet connection, and the button does not appear in Firefox.

Laptop A works as is, because `localhost` counts as a secure address. Laptop B opens the game over plain `http://`, and the browser blocks the microphone there. To allow it on Laptop B, once:

1. Open `chrome://flags/#unsafely-treat-insecure-origin-as-secure` (in Edge: `edge://flags/#unsafely-treat-insecure-origin-as-secure`).
2. Type Laptop A's address, for example `http://192.168.1.23:8000`, and set the option to **Enabled**.
3. Press **Relaunch**, open `/team/b` again, press Speak and allow the microphone.

If Laptop A's address changes on the event Wi-Fi, update the address in that setting.

## If Laptop A fails

Run `uv run jailbreak` on Laptop B and open its own `/team/b`; Laptop A (once it is back) opens Laptop B's address with `/team/a`. Scores from the failed laptop are not carried over.

## Changing the game

Everything lives in `config.json`. Each round has a `title`, a `difficulty` label, a base time in `minutes`, its own `hint`, and the guard `prompt` (`{code}` marks where the secret goes). `"easier_option": 2` on Round 3 is what offers the Round 2 guard as a Medium choice. `speech_lang` sets the language the Speak button listens for (`en-US` by default; for example `id-ID` for Indonesian). Restart the server after editing it. The host can still change every round's time from the Host panel during the event.

The guard tries `gemini-3.5-flash-lite` first, then `gemini-3.1-flash-lite`, then `gemma-4-26b-a4b-it`. A model that hits a rate limit or an error is skipped for 60 seconds. If Gemma keeps failing, swap it for `gemma-4-31b-it` in `config.json`.

## Files the server writes

- `state.json`: the current session, so a restart keeps the scores.
- `results.jsonl`: one line per finished or stopped session. Delete both files to start the event from session 1.

## Tests

`uv run pytest`
