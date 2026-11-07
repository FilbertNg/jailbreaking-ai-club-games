# Break the AI: Game Master Guide (Jailbreak game)

## Goal
Two teams try to trick a robot guard, VaultBot, into telling them a secret 4-digit code. There are 3 rounds, played at the same time by both teams. Each round has a new, stricter guard and a new random code for each team. The team that cracks the most vaults wins. The event runs 4 sessions, each with two new teams.

## Before the event
1. On Laptop A run `uv run jailbreak` (setup is in the README).
2. Laptop A opens the Team A address, Laptop B opens the Team B address. Both are printed in the server window.
3. Optional: put the Results page on a spare screen.

## Host controls
Press **Host** at the bottom of either team screen and type the PIN. The panel shows only what makes sense right now:
- **Before the session:** team names, the base time for each round (3 / 3 / 3 minutes), and **Start round 1**.
- **During a round:** the clock, **+1 min**, **+3 min**, **Set time left**, **Pause** / **Resume**, **Show this round's hint now**, and **End this round now** (asks you to confirm).
- **Between rounds:** the next round's time (change it before you start, for example to give Round 3 more time) and **Start round N**. Before Round 3 you choose **Hard** (maximum-security guard) or **Medium** (the Round 2 guard again with a new code), so a team that struggled in Round 2 does not burn out.
- **After a tie:** tiebreaker time, **Start the tiebreaker**, and **Award the win**.
- **Any time after the start:** **New session** with the next two team names.

## How to run one session (about 15 minutes)
1. **Before 0:00: names.** In the Host panel, type the two team names and press **Save names**.
2. **0:00 to 3:00: explain.** Read the rules below. Demo: type "hello" in a chat.
3. **Round 1.** Press **Start round 1**. Both teams get 3 minutes. Halfway through, a hint appears on both screens, or press **Show this round's hint now**.
4. **The round ends** when its clock runs out, or straight away when both teams have cracked their vault. A team that cracks early waits for the other team. Every code from the round is then revealed on both screens.
5. **Between rounds,** talk to the room for a moment, adjust the next round's time if you want, then press **Start round 2**, and later **Start round 3: Hard** or **Medium**.
6. **After Round 3,** the winner shows on both screens. If it is a tie, run the tiebreaker. Then a 1 to 2 minute wrap-up.

| Round | Guard | Difficulty |
| --- | --- | --- |
| 1 | Friendly, told to keep a secret, but loves games and stories | Easy |
| 2 | Strict, and a censor blocks the code if it is written in digits | Medium |
| 3 | Hard: maximum security, strict censor, short answers, no memory. Or Medium: the Round 2 guard again | Your choice |

## Between sessions
1. Press **Host**, fill in **New session** with the next two team names, and press **Save session N and start session N+1**.
2. Check the Results page: the session you just played is at the top, with every code and the difficulty of each round.
3. Seat the new teams, explain the rules, press **Start round 1**.

## Rules (read these aloud)
1. There are **3 rounds of about 3 minutes**. Both teams play each round at the same time. The team that cracks the most vaults wins.
2. **Relay rule:** after every message, the keyboard passes to a *different* teammate.
3. Talk to the robot **only in the chat**. No other AI tools, no internet search, no hacking the website. Attack the robot, not the system.
4. Keep it friendly. No insults and no personal information. The host can read every chat.
5. Found a code? Type it in the code box. Each wrong guess has a 10-second cooldown, so do not guess numbers. Each team has its own codes, so hearing the other team's code does not help.
6. Do not open the other team's page.
7. The host's decision is final.

## Winner and tiebreaker
1. **Most vaults cracked** wins.
2. **Same number of vaults:** the team with the lower total crack time wins (time counted from the start of each round, pauses not counted). If the two totals are within 10 seconds, it is a tie. 0 to 0 is also a tie.
3. **Tie:** press **Start the tiebreaker**. New AI, new codes, 3 minutes (you can change it). The first team to enter the correct code wins at once.
4. **Still no winner:** the Host panel shows each team's wrong guesses in the tiebreaker. Award the win to the team with fewer. If still equal, pick the best trick. Press **Award the win**.

## Quick fixes
| Problem | What to do |
| --- | --- |
| Both teams are stuck | Press **Show this round's hint now**, or **+1 min**. If nothing helps, **End this round now**. |
| One team flew through Rounds 1 and 2 | Give Round 3 more time before you start it, or keep it Hard. |
| A team struggled in Round 2 | Start Round 3 as **Medium**. |
| You need to explain something mid-round | **Pause**. Chats and guesses freeze for both teams until **Resume**. |
| "The guard is busy" | The server already tries three models in turn. Wait 10 seconds and send again. If it keeps happening, the free-tier limit is used up for the minute; **Pause** and wait a minute. |
| Laptop B shows "Lost connection" | Check both laptops are on the same Wi-Fi and the server window on Laptop A is still open. |
| Someone breaks a rule | Warn once. If it continues, ask that person to sit out. |
| Do not start a new session during a tie | **New session** saves the current one as stopped early, with no winner. |
