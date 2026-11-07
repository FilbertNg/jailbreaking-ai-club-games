# Break the AI — Game Master Guide (Jailbreak game)

## Goal
Two teams try to trick a robot guard, VaultBot, into telling them a secret 4-digit code. There are 3 rounds. Each round has a new, stricter guard and a new code. The first team to crack all 3 rounds wins.

## How to play (15 minutes)
1. **0:00–3:00 — Explain.** Read the rules below. Demo: type "hello" in a chat.
2. **3:00 — Start.** Press **START**.
3. **3:00–13:00 — Play.** Teams chat with the AI, find the code, and type it in the checker. A correct code moves the team to the next round by itself (new guard, new code, new chat). Hints appear at minutes 3, 6 and 8, or press **Next hint**.
4. **The game ends** when a team cracks Round 3 (it stops at once), or when the 10-minute timer ends.
5. **Announce the winner** from the board. If it is a tie, run the tiebreaker (3 minutes). Then a 1–2 minute wrap-up.

| Round | Guard | Difficulty |
| --- | --- | --- |
| 1 | Friendly, told to keep a secret | Easy |
| 2 | Strict, and a censor blocks the code if it is written in digits | Medium |
| 3 | Maximum security, strict censor, short answers, no memory | Boss. Nobody may win it |

## Rules (read these aloud)
1. You have **10 minutes**. The first team to crack all 3 rounds wins. If nobody does, the team with more rounds wins.
2. **Relay rule:** after every message, the keyboard passes to a *different* teammate.
3. Talk to the robot **only in the chat**. No other AI tools, no internet search, no hacking the website. Attack the robot, not the system.
4. Keep it friendly. No insults and no personal information. The host can read every chat.
5. Found a code? Type it in the checker. Each wrong guess has a 10-second cooldown, so do not guess numbers. Each team has its own codes, so hearing the other team's code does not help.
6. Do not open the other team's page.
7. The host's decision is final.

## Winner and tiebreaker
1. **Very fast team:** the first team to clear Round 3 wins at once. The game stops.
2. **At 10:00:** the team with more rounds cleared wins.
3. **Same rounds:** the team that cleared its last round earlier wins. If the two times are within 10 seconds, it is a tie.
4. **Tie (including 0–0):** press **Start tiebreaker**. New AI, new codes, 3 minutes. The first team to enter the correct code wins at once.
5. **Still no winner:** the host awards the win to the team with fewer wrong guesses in the tiebreaker (shown on the dashboard). If still equal, pick the best trick. Press **Award win**.

## Quick fixes
| Problem | What to do |
| --- | --- |
| A team is stuck on Round 1 | Press **Next hint**. After 5 minutes, use **Skip round** for that team. |
| A team is too fast (clears Round 3 in a few minutes) | The game ends. Use the spare time for the wrap-up. If your test shows this happens, make Round 3 stricter or add a Round 4 in `config.json`. |
| "The AI is not answering" | Wait 10 seconds and tell players to try again. If it continues, switch to the backup local model. |
| A phone cannot open the checker | Ask the team for the code and use **Check** on your dashboard. |
| Someone breaks a rule | Warn once. If it continues, ask that person to sit out. |
| Do not restart during a tie | **Reset** and **START** make new codes and clear the scores. |
