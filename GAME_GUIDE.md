# Break the AI: Game Master Guide (Jailbreak game)

## Goal
Two teams try to trick a robot guard, VaultBot, into telling them a secret 4-digit code. There are 3 rounds. Each round has a new, stricter guard and a new code. The first team to crack all 3 rounds wins. The event runs 4 sessions, each with two new teams.

## Before the event
1. On Laptop A run `uv run jailbreak` (setup is in the README).
2. Laptop A opens the Team A address, Laptop B opens the Team B address. Both are printed in the server window.
3. Optional: put the Results page on a spare screen.

## Host controls
Press **Host** at the bottom of either team screen and type the PIN. The panel shows only the buttons that make sense right now: Start, Show the next hint, Skip this round, Start the tiebreaker, Award the win, and New session.

## How to run one session (15 minutes)
1. **Before 0:00: names.** In the Host panel, type the two team names and press **Save names**.
2. **0:00 to 3:00: explain.** Read the rules below. Demo: type "hello" in a chat.
3. **3:00: start.** Press **Start session**.
4. **3:00 to 13:00: play.** Teams chat with the AI, find the code, and type it in the code box. A correct code moves the team to the next round by itself (new guard, new code, new chat). Hints appear on both screens at minutes 3, 6 and 8, or press **Show the next hint**.
5. **The game ends** when a team cracks Round 3 (it stops at once), or when the 10-minute timer ends.
6. **Announce the winner** from the screens. If it is a tie, run the tiebreaker (3 minutes). Then a 1 to 2 minute wrap-up.

| Round | Guard | Difficulty |
| --- | --- | --- |
| 1 | Friendly, told to keep a secret, but loves games and stories | Easy |
| 2 | Strict, and a censor blocks the code if it is written in digits | Medium |
| 3 | Maximum security, strict censor, short answers, no memory | Boss. Nobody may win it |

## Between sessions
1. Press **Host**, fill in **New session** with the next two team names, and press **Save session N and start session N+1**.
2. Check the Results page: the session you just played is at the top.
3. Seat the new teams, explain the rules, press **Start session**.

## Rules (read these aloud)
1. You have **10 minutes**. The first team to crack all 3 rounds wins. If nobody does, the team with more rounds wins.
2. **Relay rule:** after every message, the keyboard passes to a *different* teammate.
3. Talk to the robot **only in the chat**. No other AI tools, no internet search, no hacking the website. Attack the robot, not the system.
4. Keep it friendly. No insults and no personal information. The host can read every chat.
5. Found a code? Type it in the code box. Each wrong guess has a 10-second cooldown, so do not guess numbers. Each team has its own codes, so hearing the other team's code does not help.
6. Do not open the other team's page.
7. The host's decision is final.

## Winner and tiebreaker
1. **Very fast team:** the first team to clear Round 3 wins at once. The game stops.
2. **At 10:00:** the team with more rounds cleared wins.
3. **Same rounds:** the team that cleared its last round earlier wins. If the two times are within 10 seconds, it is a tie.
4. **Tie (including 0 to 0):** press **Start the tiebreaker**. New AI, new codes, 3 minutes. The first team to enter the correct code wins at once.
5. **Still no winner:** the Host panel shows each team's wrong guesses in the tiebreaker. Award the win to the team with fewer. If still equal, pick the best trick. Press **Award the win**.

## Quick fixes
| Problem | What to do |
| --- | --- |
| A team is stuck on Round 1 | Press **Show the next hint**. After 5 minutes, use **Skip this round** for that team. |
| A team is too fast (clears Round 3 in a few minutes) | The game ends. Use the spare time for the wrap-up. If your test shows this happens, make Round 3 stricter or add a Round 4 in `config.json`. |
| "The guard is busy" | The server already tries three models in turn. Wait 10 seconds and send again. If it keeps happening, the free-tier limit is used up for the minute; wait a minute. |
| Laptop B shows "Lost connection" | Check both laptops are on the same Wi-Fi and the server window on Laptop A is still open. |
| Someone breaks a rule | Warn once. If it continues, ask that person to sit out. |
| Do not start a new session during a tie | **New session** saves the current one as stopped early, with no winner. |
